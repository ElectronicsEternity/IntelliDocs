# ========================================
# File: retriever.py
# ========================================
#
# Purpose
# -------
# Retrieve relevant chunks for one question.
#
# Responsibilities
# ----------------
# - Run vector similarity search.
# - Run hierarchy-aware node-vector search.
# - Recognize exact structural identifiers.
# - Combine both result lists without duplicates.
#
# ========================================

from app.constants import SIMILARITY_THRESHOLD
from app.rag.embedder import Embedder
from app.rag.document_router import DocumentRouter
from app.config import settings
from app.services.usage.ai_usage import ai_usage_context
from app.storage.postgres_vector_store import (
    PostgresVectorStore,
)


# ==========================================================
# Retriever
# ==========================================================

class Retriever:

    def __init__(
        self,
        embedder: Embedder,
        vector_store: PostgresVectorStore,
    ):
        self.embedder = embedder
        self.vector_store = vector_store
        self.document_router = DocumentRouter(vector_store)

    # Run vector and hierarchy retrieval together.
    def retrieve(
        self,
        question: str,
        owner_id: str,
        top_k: int | None = None,
    ) -> list[dict]:
        # Use the central final allowance when no request-specific limit is set.
        top_k = settings.RAG_TOP_K if top_k is None else top_k
        with ai_usage_context(user_id=owner_id, embedding_activity="query_embedding"):
            question_embedding = self.embedder.generate_embedding(question)

        selected_documents, broad_fallback = self.document_router.select(
            question=question,
            owner_id=owner_id,
            embedding=question_embedding,
        )
        if not selected_documents:
            return []

        per_document_results = []
        for document in selected_documents:
            document_id = document["document_id"]
            candidate_limit = (
                settings.DOCUMENT_FALLBACK_CHUNKS_PER_DOCUMENT
                if broad_fallback else settings.RAG_DOCUMENT_TOP_K
            )
            # Keep the established three retrieval paths unchanged, but run
            # them independently inside each selected document.
            vector_results = self.vector_store.search(
                owner_id=owner_id,
                embedding=question_embedding,
                top_k=candidate_limit,
                document_id=document_id,
            )
            node_results = self.vector_store.search_node_hierarchy(
                owner_id=owner_id,
                embedding=question_embedding,
                top_k=candidate_limit,
                document_id=document_id,
            )
            identifier_results = self.vector_store.search_exact_identifier(
                owner_id=owner_id,
                query=question,
                embedding=question_embedding,
                # Exact references must retain every child, even when the
                # document router uses its small semantic fallback allowance.
                top_k=None,
                document_id=document_id,
            )
            combined = self._combine_results(
                vector_results,
                node_results,
                identifier_results,
                candidate_limit,
            )
            for result in combined:
                result["document_selection_score"] = document["combined_score"]
            per_document_results.append(combined)

        # Preserve complete exact-reference bundles in document-score order.
        # Different documents can share an identifier; their document labels
        # remain attached so the answer model can distinguish the provisions.
        anchors = []
        supplements = []
        for group in per_document_results:
            # Keep each matched root and its descendants together until both
            # selection limits have been applied. Other chunks are single units.
            document_anchors = {}
            for result in group:
                if "exact_identifier" in result.get("match_types", []):
                    unit_id = result["retrieval_unit_id"]
                    document_anchors.setdefault(unit_id, []).append(result)
            anchors.extend(document_anchors.values())
            supplements.append([
                result for result in group
                if "exact_identifier" not in result.get("match_types", [])
            ])
        # Count section bundles, not their child chunks, against the final limit.
        # Preserve every explicit section even if those units exceed top_k.
        remaining = max(0, top_k - len(anchors))
        selected_chunks = [chunk for unit in anchors for chunk in unit]
        selected_chunks.extend(self._round_robin(supplements, remaining))
        # Overlapping requested sections can share children. Keep the first copy
        # in hierarchy order, preserving all original citation fields.
        unique_chunks = {}
        for chunk in selected_chunks:
            unique_chunks.setdefault(chunk["chunk_id"], chunk)
        return list(unique_chunks.values())

    @staticmethod
    def _round_robin(result_groups: list[list[dict]], top_k: int) -> list[dict]:
        # A full exact-reference bundle can leave no room for supplements.
        if top_k <= 0:
            return []
        results = []
        seen = set()
        max_length = max((len(group) for group in result_groups), default=0)
        for rank in range(max_length):
            for group in result_groups:
                if rank >= len(group):
                    continue
                result = group[rank]
                if result["chunk_id"] in seen:
                    continue
                seen.add(result["chunk_id"])
                results.append(result)
                if len(results) == top_k:
                    return results
        return results

    # Fuse ranked lists while retaining one copy per chunk.
    def _combine_results(
        self,
        vector_results: list[dict],
        node_results: list[dict],
        identifier_results: list[dict],
        top_k: int,
    ) -> list[dict]:
        combined = {}
        # # random number to control
        # how strongly result rank affects the combined score.
        rank_offset = 60
        search_paths = (
            ("chunk_vector", vector_results, 1.0),
            ("node_vector", node_results, 1.0),
            ("exact_identifier",identifier_results, 2.0,),
        )

        # Add reciprocal-rank credit from each search path.
        for search_type, results, weight in search_paths:
            # Assign each result a rank based on
            # its relevance order.
            # Start ranking from 1 instead of 0
            for rank, result in enumerate(results, start=1):
                is_exact_identifier = (
                    search_type == "exact_identifier"
                )

                # Semantic searches require the threshold.
                # Exact structural matches bypass it.
                if (
                    not is_exact_identifier
                    and
                    result["similarity"]
                    < SIMILARITY_THRESHOLD
                ):
                    continue

                chunk_id = result["chunk_id"]

                if chunk_id not in combined:
                    combined[chunk_id] = result.copy()
                    # hybrid score starts at 0.0
                    combined[chunk_id]["hybrid_score"] = 0.0
                    # create empty list to store match types
                    combined[chunk_id]["match_types"] = []

                stored = combined[chunk_id]

                # Preserve fields unique to either search path.
                for key, value in result.items():
                    if key not in stored:
                        stored[key] = value

                stored["hybrid_score"] += weight / (
                    rank_offset + rank
                )
                stored["match_types"].append(search_type)
                if is_exact_identifier:
                    # Document ID prevents equal section IDs across documents
                    # from being mistaken for the same retrieval unit.
                    root_id = result.get("exact_anchor_id", "matched-section")
                    stored["retrieval_unit_id"] = (
                        f"{result.get('document_id', '')}:section:{root_id}"
                    )

        ranked_results = sorted(
            combined.values(),
            key=lambda result: result["hybrid_score"],
            reverse=True,
        )

        # When the question names an exact structural node, keep that node's
        # complete subtree ahead of global semantic results. This prevents
        # individually strong but unrelated chunks from splitting the anchor.
        anchored_results = []
        anchored_ids = set()
        for result in identifier_results:
            chunk_id = result["chunk_id"]
            if chunk_id in anchored_ids or chunk_id not in combined:
                continue
            anchored_results.append(combined[chunk_id])
            anchored_ids.add(chunk_id)

        # Existing reciprocal-rank fusion remains responsible for filling the
        # context after the mandatory anchor bundle has been included.
        supplementary_results = [
            result
            for result in ranked_results
            if result["chunk_id"] not in anchored_ids
        ]
        # A section's complete subtree consumes one slot, regardless of size.
        # Separate explicitly requested roots consume separate slots.
        anchor_unit_count = len({
            result["retrieval_unit_id"] for result in anchored_results
        })
        remaining = max(0, top_k - anchor_unit_count)
        return anchored_results + supplementary_results[:remaining]
