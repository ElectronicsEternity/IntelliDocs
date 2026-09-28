from app.indexing.table_matrix import validate_table_matrices


def _profile():
    return {
        "tables": [{
            "table_id": "T1", "title": "Rates", "start_page": 3, "end_page": 4,
            "column_count": 2, "data_row_count": 2,
        }]
    }


def test_table_matrix_accepts_matching_dimensions_and_source_pages():
    result = {
        "tables": [{
            "table_id": "T1", "title": "Rates", "start_page": 3, "end_page": 4,
            "column_count": 2, "columns": ["Area", "Rate"], "row_count": 2,
            "rows": [
                {"row_number": 1, "cells": ["City", "10"], "source_pages": [3]},
                {"row_number": 2, "cells": ["Other", "8"], "source_pages": [4]},
            ],
        }]
    }
    assert validate_table_matrices(result, _profile()) == ()


def test_table_matrix_rejects_bad_row_geometry_and_page():
    result = {
        "tables": [{
            "table_id": "T1", "title": "Rates", "start_page": 3, "end_page": 4,
            "column_count": 2, "columns": ["Area", "Rate"], "row_count": 1,
            "rows": [{"row_number": 2, "cells": ["City"], "source_pages": [5]}],
        }]
    }
    errors = validate_table_matrices(result, _profile())
    assert any("row count" in error for error in errors)
    assert any("has number" in error for error in errors)
    assert any("has 1 cells" in error for error in errors)
    assert any("outside 3-4" in error for error in errors)
