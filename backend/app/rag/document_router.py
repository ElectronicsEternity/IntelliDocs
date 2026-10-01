"""Select likely documents before running the existing chunk retrieval."""

import logging
import re

from app.config import settings


# Use the backend's configured handler so routing scores appear in its log.
LOGGER = logging.getLogger("uvicorn.error.document_router")
WORD_PATTERN = re.compile(r"[a-z0-9]+", re.IGNORECASE)
STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "does", "for",
    "from", "how", "in", "is", "it", "of", "on", "or", "the", "to",
    "what", "when", "where", "which", "who", "with",
    "pdf",
}


def normalize_text(value: str | None) -> str:
    """Normalize punctuation and whitespace for deterministic name matching."""
    return " ".join(WORD_PATTERN.findall((value or "").lower()))


def meaningful_words(value: str | None) -> set[str]:
    """Return useful comparison words without common question filler."""
    return {
        word for word in normalize_text(value).split()
        if word not in STOP_WORDS
    }


def derive_topics(hierarchy: dict) -> list[str]:
    """Build a deduplicated topic list from existing hierarchy node titles."""
    topics = []
    seen = set()

    def visit(node: object) -> None:
        if not isinstance(node, dict):
            return
        title = " ".join(str(node.get("title") or "").split())
        normalized = normalize_text(title)
        if title and normalized not in seen:
            seen.add(normalized)
            topics.append(title)
        for child in node.get("children") or []:
            visit(child)

    visit(hierarchy)
    return topics


class DocumentRouter:
    """Score owned documents using only the three approved selection signals."""

    def __init__(self, vector_store):
        self.vector_store = vector_store

    def select(self, *, question: str, owner_id: str, embedding) -> tuple[list[dict], bool]:
        candidates = self.vector_store.list_document_routing_candidates(
            owner_id=owner_id,
            embedding=embedding,
        )
        scored = [self._score(question, candidate) for candidate in candidates]
        scored.sort(key=lambda item: item["combined_score"], reverse=True)

        exact = [item for item in scored if item["exact_name_match"]]
        relevant = [
            item for item in scored
            if item["combined_score"] >= settings.DOCUMENT_ROUTING_MIN_SCORE
            and not item["exact_name_match"]
        ]
        # A named document is always primary, while other strongly relevant
        # documents remain available as cross-document evidence.
        selected = (exact + relevant)[:settings.DOCUMENT_ROUTING_MAX_DOCUMENTS]
        broad_fallback = not selected
        if broad_fallback:
            selected = scored

        selected_ids = {item["document_id"] for item in selected}
        for order, item in enumerate(scored, start=1):
            item["selection_order"] = order
            item["selected"] = item["document_id"] in selected_ids
            LOGGER.info("document_selection %s", item)
        return selected, broad_fallback

    def _score(self, question: str, candidate: dict) -> dict:
        normalized_question = normalize_text(question)
        title = normalize_text(candidate.get("document_title"))
        filename = normalize_text(candidate.get("filename"))
        title_match = self._name_match(normalized_question, title)
        filename_match = self._name_match(normalized_question, filename)
        name_match = max(title_match, filename_match)
        exact_name_match = bool(
            (title and title in normalized_question)
            or (filename and filename in normalized_question)
        )

        question_words = meaningful_words(question)
        matched_titles = []
        hierarchy_score = 0.0
        for topic in candidate.get("topics") or []:
            topic_words = meaningful_words(topic)
            if not topic_words:
                continue
            overlap = len(question_words & topic_words) / len(topic_words)
            if overlap:
                matched_titles.append(topic)
                hierarchy_score = max(hierarchy_score, overlap)

        description_similarity = max(
            0.0,
            float(candidate.get("description_similarity") or 0.0),
        )
        # Apply name weight only when the question meaningfully names this
        # document. Otherwise normalize the description/topic weights so an
        # unnamed document is not penalized for the absent name signal.
        uses_name = exact_name_match or (
            name_match >= settings.DOCUMENT_NAME_MATCH_MIN_SCORE
        )
        name_weight = settings.DOCUMENT_TITLE_FILENAME_WEIGHT if uses_name else 0.0
        description_weight = settings.DOCUMENT_DESCRIPTION_WEIGHT
        hierarchy_weight = settings.DOCUMENT_HIERARCHY_TITLE_WEIGHT
        total_weight = name_weight + description_weight + hierarchy_weight
        combined = (
            name_weight * name_match
            + description_weight * description_similarity
            + hierarchy_weight * hierarchy_score
        ) / total_weight if total_weight > 0 else 0.0
        return {
            "document_id": str(candidate["document_id"]),
            "document_title": candidate.get("document_title"),
            "filename": candidate.get("filename"),
            "title_match": round(title_match, 6),
            "filename_match": round(filename_match, 6),
            "description_similarity": round(description_similarity, 6),
            "matching_hierarchy_titles": matched_titles,
            "combined_score": round(combined, 6),
            "exact_name_match": exact_name_match,
            "uses_name_weight": uses_name,
        }

    @staticmethod
    def _name_match(question: str, name: str) -> float:
        if not name:
            return 0.0
        if name in question:
            return 1.0
        name_words = meaningful_words(name)
        if not name_words:
            return 0.0
        return len(meaningful_words(question) & name_words) / len(name_words)
