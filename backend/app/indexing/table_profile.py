"""Schema, prompt, and validation for visually profiled PDF tables."""

TABLE_BORDER_STYLES = {"bordered", "borderless", "mixed", "uncertain"}
TABLE_EXTRACTION_MODES = {"regular_matrix", "semantic_records"}

# Purpose: detect common label/value publication-history layouts in front matter.
FRONT_MATTER_FIELD_GROUPS = (
    ("first enacted", "originally enacted"),
    ("revised", "revision"),
    ("latest amendment", "last amended"),
    ("previous reprint", "reprint"),
    ("date of publication", "published on"),
    ("date of commencement", "commencement date"),
)


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

A repeated front-matter label/value layout is a borderless table, not ordinary
two-column prose. For example, identify the following as one two-column table
even when it has no borders and no printed column headings:

First enacted       | 1955 (F.M. Ordinance No. 38 of 1955)
Revised             | 1981 (Act 265 w.e.f. 18 February 1982)
Latest amendment    | 1 January 2023
Previous reprints   | 1975; 2001; 2006

Include genuine data tables in front matter, appendices, schedules, or other
standalone locations even when they do not belong to a legal section or heading.
Do not invent a hierarchy parent. Return their physical page range and table
data normally; the application resolves hierarchy ownership locally.

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


def find_front_matter_table_pages(page_texts: list[str]) -> tuple[int, ...]:
    """Find pages with several recognizable label/value metadata fields."""
    candidate_pages = []

    # Front matter is expected near the beginning; limiting the scan avoids body prose.
    for page_number, page_text in enumerate(page_texts[:12], 1):
        normalized_text = " ".join((page_text or "").lower().split())

        # Count field families rather than raw phrases so synonyms cannot double-count.
        matched_field_groups = sum(
            1
            for alternatives in FRONT_MATTER_FIELD_GROUPS
            if any(phrase in normalized_text for phrase in alternatives)
        )

        # Three separate metadata fields provide conservative table-like evidence.
        if matched_field_groups >= 3:
            candidate_pages.append(page_number)

    return tuple(candidate_pages)


def build_table_profile_repair_prompt(
    previous_profile: dict,
    errors: tuple[str, ...],
) -> str:
    """Request one complete correction using precise local validation failures."""
    import json

    error_text = "\n".join(f"- {error}" for error in errors)
    previous_json = json.dumps(previous_profile, ensure_ascii=False)
    return f"""{TABLE_PROFILE_PROMPT}

CORRECTION REQUIRED

The previous table profile failed local validation:
{error_text}

Return the complete corrected table profile, preserving valid tables and adding
every omitted table. A page named in an error contains repeated label/value
front-matter records and must be represented as a borderless table.

PREVIOUS PROFILE
{previous_json}
"""


def validate_table_profile(
    profile: dict,
    expected_pages: int,
    required_front_matter_pages: tuple[int, ...] = (),
) -> tuple[str, ...]:
    """Return deterministic cross-field errors beyond JSON Schema checks."""
    errors = []
    if profile.get("page_count") != expected_pages:
        errors.append(
            f"page_count {profile.get('page_count')} does not match PDF page count {expected_pages}."
        )
    seen_ids = set()
    covered_pages = set()
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
        covered_pages.update(range(start, end + 1))
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

    # Source-derived evidence prevents a valid-looking profile from silently omitting
    # a repeated label/value table such as the Employment Act publication history.
    for page_number in required_front_matter_pages:
        if page_number not in covered_pages:
            errors.append(
                "No table covers front-matter page "
                f"{page_number}, which contains repeated label/value records."
            )
    return tuple(errors)
