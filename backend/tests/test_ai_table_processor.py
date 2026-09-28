from app.ingestion.ai_table_processor import AIVisualTableProcessor


def test_model_matrix_is_normalized_for_existing_chunker():
    normalized = AIVisualTableProcessor._normalize({
        "table_id": "table-1",
        "title": "Rates",
        "start_page": 4,
        "end_page": 5,
        "column_count": 2,
        "columns": ["Area", "Rate"],
        "row_count": 1,
        "rows": [{
            "row_number": 1,
            "cells": ["City", "RM1,200"],
            "source_pages": [4, 5],
        }],
    }, 1)

    assert normalized["page_numbers"] == [4, 5]
    assert normalized["row_count"] == 2
    assert normalized["column_count"] == 2
    assert [cell["value"] for cell in normalized["cells"]] == [
        "Area", "Rate", "City", "RM1,200",
    ]
    assert all(cell["source_table"] == 1 for cell in normalized["cells"])
