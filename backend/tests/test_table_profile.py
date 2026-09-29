from app.indexing.table_profile import (
    TABLE_PROFILE_PROMPT,
    find_front_matter_table_pages,
    validate_table_profile,
)


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


# Purpose: preserve the agreed distinction between prose and label/value metadata.
def test_prompt_explicitly_includes_borderless_publication_history_example():
    assert "First enacted       | 1955" in TABLE_PROFILE_PROMPT
    assert "repeated front-matter label/value layout" in TABLE_PROFILE_PROMPT


# Purpose: detect the Employment Act page-2 publication-history layout locally.
def test_finds_repeated_front_matter_label_value_page():
    page_texts = [
        "EMPLOYMENT ACT 1955",
        (
            "First enacted 1955 Revised 1981 Latest amendment made by Act A1651 "
            "PREVIOUS REPRINTS First Reprint 1975 Second Reprint 2001"
        ),
        "PART I PRELIMINARY",
    ]

    assert find_front_matter_table_pages(page_texts) == (2,)


# Purpose: reject a table profile that silently omits locally detected front matter.
def test_table_profile_requires_detected_front_matter_page():
    profile = {"page_count": 2, "tables": []}

    errors = validate_table_profile(
        profile,
        expected_pages=2,
        required_front_matter_pages=(2,),
    )

    assert any("front-matter page 2" in error for error in errors)
