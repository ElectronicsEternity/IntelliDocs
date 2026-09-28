from app.indexing.table_profile import validate_table_profile


def test_table_profile_validates_dimensions_and_regions():
    profile = {
        "page_count": 2,
        "tables": [{
            "table_id": "t1", "title": "Rates", "start_page": 1, "end_page": 2,
            "border_style": "bordered", "column_count": 2,
            "header_row_count": 1, "data_row_count": 3,
            "column_headings": ["Name", "Rate"],
            "page_regions": [
                {"page": 1, "left": 10, "top": 20, "right": 900, "bottom": 990},
                {"page": 2, "left": 10, "top": 10, "right": 900, "bottom": 500},
            ],
        }],
    }
    assert validate_table_profile(profile, 2) == ()


def test_table_profile_rejects_missing_page_and_heading():
    profile = {
        "page_count": 2,
        "tables": [{
            "table_id": "t1", "title": "Rates", "start_page": 1, "end_page": 2,
            "column_count": 2, "column_headings": ["Only one"],
            "page_regions": [{"page": 1, "left": 10, "top": 20, "right": 900, "bottom": 990}],
        }],
    }
    errors = validate_table_profile(profile, 2)
    assert any("heading count" in error for error in errors)
    assert any("do not cover" in error for error in errors)
