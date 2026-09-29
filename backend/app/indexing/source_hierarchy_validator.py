"""Validate hierarchy completeness against conservative source-text evidence."""

import re


# Purpose: locate each explicit physical-page marker without consuming page text.
PAGE_LABEL_PATTERN = re.compile(
    r"(?m)^\[\[PAGE_LABEL:\s*(?P<label>\d+)\]\][^\S\r\n]*\r?$",
)

# Purpose: identify only clear legal section openings such as "67. Rest day".
SECTION_OPENING_PATTERN = re.compile(
    r"(?m)^\s*(?P<identifier>\d{1,3}[A-Z]{0,3})\.\s+\S"
)

# Purpose: detect whether the source clearly contains numbered subsection openings.
SUBSECTION_OPENING_PATTERN = re.compile(
    r"(?m)^\s*\((?P<identifier>\d{1,2}[A-Z]?)\)\s+\S"
)


def _walk_nodes(node: object):
    """Yield every dictionary node without assuming the response is valid."""
    if not isinstance(node, dict):
        return

    # Yield the current node before its descendants to preserve document order.
    yield node

    # Invalid children are ignored here because the schema validator reports them.
    children = node.get("children", [])
    if not isinstance(children, list):
        return

    # Recursively expose every descendant for type and identifier comparisons.
    for child in children:
        yield from _walk_nodes(child)


def _source_pages(document_text: str) -> dict[int, str]:
    """Return the exact PAGE_LABEL-to-text mapping sent to OpenAI."""
    markers = list(PAGE_LABEL_PATTERN.finditer(document_text))
    pages: dict[int, str] = {}

    # Slice between consecutive markers so any number of blank lines is safe.
    for index, marker in enumerate(markers):
        text_start = marker.end()
        text_end = (
            markers[index + 1].start()
            if index + 1 < len(markers)
            else len(document_text)
        )
        pages[int(marker.group("label"))] = document_text[text_start:text_end]

    return pages


def _main_body_range(nodes: list[dict], page_count: int) -> tuple[int, int]:
    """Bound evidence checks to the legal body, excluding contents and schedules."""
    body_pages = [
        node.get("start_page")
        for node in nodes
        if node.get("type") in {
            "HEADING",
            "PART",
            "CHAPTER",
            "ARTICLE",
            "SECTION",
        }
        and type(node.get("start_page")) is int
    ]
    terminal_pages = [
        node.get("start_page")
        for node in nodes
        if node.get("type") in {"SCHEDULE", "APPENDIX", "FORM"}
        and type(node.get("start_page")) is int
    ]

    # Start where substantive legal structure first appears when the model supplied it.
    start_page = min(body_pages, default=1)

    # Stop immediately before schedules or appendices to avoid their numbered rows.
    end_page = min(terminal_pages, default=page_count + 1) - 1
    return start_page, max(start_page, end_page)


def validate_source_hierarchy_completeness(
    hierarchy: object,
    document_text: str,
    page_count: int | None,
) -> tuple[str, ...]:
    """Reject a structurally valid response that clearly omits provision families."""
    if not isinstance(hierarchy, dict) or not page_count:
        return ()

    nodes = list(_walk_nodes(hierarchy))

    # Apply legal-provision checks only when the hierarchy itself identifies legal form.
    has_legal_structure = any(
        node.get("type") in {
            "PART",
            "CHAPTER",
            "ARTICLE",
            "SECTION",
            "SUBSECTION",
            "CLAUSE",
            "SCHEDULE",
        }
        for node in nodes
    )
    if not has_legal_structure:
        return ()

    pages = _source_pages(document_text)
    start_page, end_page = _main_body_range(nodes, page_count)

    # Join only the likely legal body pages before searching for provision markers.
    body_text = "\n".join(
        pages.get(page_number, "")
        for page_number in range(start_page, end_page + 1)
    )

    # Normalize printed identifiers so "67." and "67" compare as the same section.
    source_sections = {
        match.group("identifier").upper()
        for match in SECTION_OPENING_PATTERN.finditer(body_text)
    }
    returned_sections = {
        str(node.get("identifier", "")).strip().rstrip(".").upper()
        for node in nodes
        if node.get("type") == "SECTION"
    }
    returned_sections.discard("")

    errors: list[str] = []

    # A legal body with several printed sections can never validly return zero sections.
    if len(source_sections) >= 5 and not returned_sections:
        sample = ", ".join(sorted(source_sections, key=_identifier_sort_key)[:8])
        errors.append(
            "The hierarchy contains zero SECTION nodes although the source has "
            f"clear section openings in the main body (for example: {sample})."
        )
    elif len(source_sections) >= 20:
        # A conservative 50% floor catches severe truncation without demanding exact OCR.
        matched_sections = source_sections & returned_sections
        if len(matched_sections) * 2 < len(source_sections):
            missing = source_sections - returned_sections
            sample = ", ".join(sorted(missing, key=_identifier_sort_key)[:8])
            errors.append(
                "The hierarchy appears severely incomplete: it returned only "
                f"{len(matched_sections)} of {len(source_sections)} clear SECTION "
                f"identifiers found in the main body. Missing examples: {sample}."
            )

    # Numerous printed subsection openings make a zero-SUBSECTION tree implausible.
    source_subsection_count = len(SUBSECTION_OPENING_PATTERN.findall(body_text))
    returned_subsection_count = sum(
        1 for node in nodes if node.get("type") == "SUBSECTION"
    )
    if source_subsection_count >= 10 and returned_subsection_count == 0:
        errors.append(
            "The hierarchy contains zero SUBSECTION nodes although the main body "
            f"contains at least {source_subsection_count} clear numbered openings."
        )

    return tuple(errors)


def _identifier_sort_key(identifier: str) -> tuple[int, str]:
    """Sort identifiers naturally so 2 appears before 10 and 67A follows 67."""
    match = re.fullmatch(r"(?P<number>\d+)(?P<suffix>[A-Z]*)", identifier)
    if not match:
        return (10**9, identifier)

    # Convert the numeric prefix once; the suffix remains lexical and case-normalized.
    return int(match.group("number")), match.group("suffix")
