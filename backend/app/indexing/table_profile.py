"""Schema, prompt, and validation for visually profiled PDF tables."""

TABLE_BORDER_STYLES = {"bordered", "borderless", "mixed", "uncertain"}
TABLE_EXTRACTION_MODES = {"regular_matrix", "semantic_records"}


TABLE_PROFILE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["document_title", "page_count", "tables"],
    "properties": {
        "document_title": {"type": "string"},
        "page_count": {"type": "integer", "minimum": 1},
        "tables": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "table_id", "title", "start_page", "end_page",
                    "border_style", "extraction_mode", "column_count", "header_row_count",
                    "data_row_count", "column_headings", "page_regions",
                ],
                "properties": {
                    "table_id": {"type": "string"},
                    "title": {"type": "string"},
                    "start_page": {"type": "integer", "minimum": 1},
                    "end_page": {"type": "integer", "minimum": 1},
                    "border_style": {
                        "type": "string",
                        "enum": sorted(TABLE_BORDER_STYLES),
                    },
                    "extraction_mode": {
                        "type": "string",
                        "enum": sorted(TABLE_EXTRACTION_MODES),
                    },
                    "column_count": {"type": "integer", "minimum": 1},
                    "header_row_count": {"type": "integer", "minimum": 0},
                    "data_row_count": {"type": "integer", "minimum": 0},
                    "column_headings": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "page_regions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["page", "left", "top", "right", "bottom"],
                            "properties": {
                                "page": {"type": "integer", "minimum": 1},
                                "left": {"type": "integer", "minimum": 0, "maximum": 1000},
                                "top": {"type": "integer", "minimum": 0, "maximum": 1000},
                                "right": {"type": "integer", "minimum": 0, "maximum": 1000},
                                "bottom": {"type": "integer", "minimum": 0, "maximum": 1000},
                            },
                        },
                    },
                },
            },
        },
    },
}


TABLE_PROFILE_PROMPT = """Inspect the complete PDF visually and return only its physical data tables.

Do not report a contents list, ordinary two-column prose, signature block, or a
schedule heading by itself as a table. Treat one table continuing over several
pages as one logical table.

For every table:
- Copy its printed title verbatim. If it has no title, provide a short stable
  label using its closest printed schedule/section heading.
- Use 1-based physical PDF pages, not printed page labels.
- border_style is bordered when visible ruling lines define the cells,
  borderless when alignment and whitespace define the columns, mixed when both
  styles are materially used, and uncertain only when the PDF is inconclusive.
- extraction_mode is regular_matrix when the table can be represented safely as
  stable rows and columns. Use semantic_records when layout, merged areas,
  indentation, cross-page continuation, or visual association carries meaning
  that a conventional grid could silently misassociate.
- column_count is the number of logical data columns after resolving merged
  header cells.
- header_row_count counts logical header levels, not wrapped text lines.
- data_row_count counts logical records. Wrapped lines and page continuations
  belong to their original record and must not be counted as extra rows.
- column_headings contains one resolved heading per logical data column. Join
  stacked header levels with " / ". Use an empty string only when a column has
  no printed heading.
- page_regions contains one entry for every physical page occupied by the
  table. Coordinates are integers from 0 to 1000 relative to page width/height.
  Enclose the complete table on that page, including headers and continuation
  rows, while excluding running headers, footers, page numbers, and unrelated
  prose. Never cut through printed characters.

Before returning, review every PDF page once more and verify that no physical
table is omitted, duplicated, or split into separate table entries.
"""


def validate_table_profile(profile: dict, expected_pages: int) -> tuple[str, ...]:
    """Return deterministic cross-field errors beyond JSON Schema checks."""
    errors = []
    if profile.get("page_count") != expected_pages:
        errors.append(
            f"page_count {profile.get('page_count')} does not match PDF page count {expected_pages}."
        )
    seen_ids = set()
    for index, table in enumerate(profile.get("tables", []), 1):
        label = f"table {index}"
        table_id = table.get("table_id")
        if table_id in seen_ids:
            errors.append(f"{label} repeats table_id {table_id!r}.")
        seen_ids.add(table_id)
        start, end = table.get("start_page"), table.get("end_page")
        if not isinstance(start, int) or not isinstance(end, int) or not (1 <= start <= end <= expected_pages):
            errors.append(f"{label} has invalid page range {start}-{end}.")
            continue
        headings = table.get("column_headings", [])
        if len(headings) != table.get("column_count"):
            errors.append(f"{label} heading count does not equal column_count.")
        regions = table.get("page_regions", [])
        region_pages = [region.get("page") for region in regions]
        expected_region_pages = list(range(start, end + 1))
        if region_pages != expected_region_pages:
            errors.append(
                f"{label} region pages {region_pages} do not cover {expected_region_pages} in order."
            )
        for region in regions:
            if not (
                region.get("left", 1001) < region.get("right", -1)
                and region.get("top", 1001) < region.get("bottom", -1)
            ):
                errors.append(f"{label} has an invalid region on page {region.get('page')}.")
    return tuple(errors)
