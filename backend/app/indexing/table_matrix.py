"""Structured output contract for model-extracted logical table matrices."""

import json


TABLE_MATRIX_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["document_title", "tables"],
    "properties": {
        "document_title": {"type": "string"},
        "tables": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "table_id", "title", "start_page", "end_page",
                    "column_count", "columns", "row_count", "rows",
                ],
                "properties": {
                    "table_id": {"type": "string"},
                    "title": {"type": "string"},
                    "start_page": {"type": "integer", "minimum": 1},
                    "end_page": {"type": "integer", "minimum": 1},
                    "column_count": {"type": "integer", "minimum": 1},
                    "columns": {"type": "array", "items": {"type": "string"}},
                    "row_count": {"type": "integer", "minimum": 0},
                    "rows": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["row_number", "cells", "source_pages"],
                            "properties": {
                                "row_number": {"type": "integer", "minimum": 1},
                                "cells": {"type": "array", "items": {"type": "string"}},
                                "source_pages": {
                                    "type": "array",
                                    "items": {"type": "integer", "minimum": 1},
                                },
                            },
                        },
                    },
                },
            },
        },
    },
}


def build_table_matrix_prompt(profile: dict, page_map: list[dict], *, semantic: bool = False) -> str:
    targets = []
    for table in profile["tables"]:
        targets.append({
            "table_id": table["table_id"],
            "title": table["title"],
            "start_page": table["start_page"],
            "end_page": table["end_page"],
            "column_count": table["column_count"],
            "expected_data_rows": table["data_row_count"],
            "expected_column_headings": table["column_headings"],
        })
    semantic_rules = """
These targets are irregular semantic tables. Reconstruct each logical record
before assigning its cells. Preserve nested identifiers and governing text.
Never carry a value into a nearby row merely because it appears visually close;
associate it only with the record it visibly governs. Because an uncertainty
field is not available in this schema, if an association cannot be determined
without guessing, fail the request instead of inventing a value.
""" if semantic else ""
    return f"""Extract only the target tables from this reduced PDF as complete logical matrices.

The attached PDF contains selected pages from a larger source PDF. All page numbers
in your response must be ORIGINAL physical PDF page numbers, using this exact map:
{json.dumps(page_map, ensure_ascii=False)}

Target tables and dimensions established by the prior whole-document visual pass:
{json.dumps(targets, ensure_ascii=False, indent=2)}

{semantic_rules}

Rules:
- Return every target table exactly once, in the listed order. Do not add tables.
- Preserve the target table_id, title, original start_page, and original end_page.
- Return exactly one resolved column heading and one cell per logical column.
- Return exactly expected_data_rows logical data rows. Do not count header rows.
- Preserve printed wording, spelling, numbers, punctuation, and symbols. Do not
  summarize, translate, correct, or invent content.
- Join wrapped printed lines that belong to one cell into one cell value.
- When a merged cell visibly governs multiple logical rows, repeat that governing
  value in every affected row so each row is independently understandable.
- When one logical row continues across a page break, combine it into one row and
  list every contributing ORIGINAL physical page in source_pages.
- Use an empty cell only when the source genuinely leaves that logical cell blank
  or not applicable; never use an empty cell for unreadable or uncertain text.
- Exclude running headers, footers, page numbers, and prose outside the table.
- Number rows consecutively from 1 within each table.

Before returning, verify all row and column counts against the target list and
re-read every selected page for omitted continuation content.
"""


def validate_table_matrices(result: dict, profile: dict) -> tuple[str, ...]:
    """Validate model matrices against the already accepted table-location profile."""
    errors = []
    expected_tables = profile.get("tables", [])
    actual_tables = result.get("tables", [])
    if len(actual_tables) != len(expected_tables):
        errors.append(
            f"Returned {len(actual_tables)} tables; expected {len(expected_tables)}."
        )
    for index, expected in enumerate(expected_tables):
        if index >= len(actual_tables):
            errors.append(f"Missing table {expected.get('table_id')!r}.")
            continue
        actual = actual_tables[index]
        label = expected.get("table_id", f"table {index + 1}")
        for field in ("table_id", "title", "start_page", "end_page", "column_count"):
            if actual.get(field) != expected.get(field):
                errors.append(
                    f"{label}: {field} {actual.get(field)!r} does not match {expected.get(field)!r}."
                )
        columns = actual.get("columns", [])
        column_count = expected.get("column_count")
        if len(columns) != column_count:
            errors.append(f"{label}: returned {len(columns)} headings; expected {column_count}.")
        expected_rows = expected.get("data_row_count")
        rows = actual.get("rows", [])
        if actual.get("row_count") != expected_rows or len(rows) != expected_rows:
            errors.append(
                f"{label}: row count field/list is {actual.get('row_count')}/{len(rows)}; "
                f"expected {expected_rows}."
            )
        page_start, page_end = expected.get("start_page"), expected.get("end_page")
        for row_index, row in enumerate(rows, 1):
            if row.get("row_number") != row_index:
                errors.append(f"{label}: row {row_index} has number {row.get('row_number')!r}.")
            if len(row.get("cells", [])) != column_count:
                errors.append(
                    f"{label}: row {row_index} has {len(row.get('cells', []))} cells; "
                    f"expected {column_count}."
                )
            pages = row.get("source_pages", [])
            if not pages:
                errors.append(f"{label}: row {row_index} has no source pages.")
            elif any(not page_start <= page <= page_end for page in pages):
                errors.append(
                    f"{label}: row {row_index} has source pages outside {page_start}-{page_end}."
                )
    return tuple(errors)
