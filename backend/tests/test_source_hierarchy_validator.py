from app.indexing.source_hierarchy_validator import (
    validate_source_hierarchy_completeness,
)


# Purpose: build the smallest hierarchy needed to exercise source completeness.
def _hierarchy(children):
    return {
        "type": "DOCUMENT",
        "language": "en",
        "identifier": "",
        "title": "",
        "opening_text": None,
        "start_page": 1,
        "children": children,
    }


# Purpose: prove that a valid-looking Parts-only result cannot hide missing sections.
def test_rejects_zero_sections_when_source_has_clear_section_openings():
    document_text = """[[PAGE_LABEL: 1]]
Cover

[[PAGE_LABEL: 2]]
PART I
1. Short title
2. Interpretation
3. Appointment
4. Appeals
5. Powers

[[PAGE_LABEL: 3]]
FIRST SCHEDULE
1. Schedule row
"""
    hierarchy = _hierarchy([
        {
            "type": "PART", "identifier": "I", "title": "PRELIMINARY",
            "opening_text": "Short title", "start_page": 2, "children": [],
        },
        {
            "type": "SCHEDULE", "identifier": "FIRST SCHEDULE", "title": "",
            "opening_text": "Schedule row", "start_page": 3, "children": [],
        },
    ])

    errors = validate_source_hierarchy_completeness(
        hierarchy,
        document_text,
        page_count=3,
    )

    assert any("zero SECTION nodes" in error for error in errors)


# Purpose: verify that schedule numbering is excluded from body completeness evidence.
def test_schedule_rows_do_not_create_false_section_omissions():
    document_text = """[[PAGE_LABEL: 1]]
Cover

[[PAGE_LABEL: 2]]
PART I
1. Short title

[[PAGE_LABEL: 3]]
FIRST SCHEDULE
1. One
2. Two
3. Three
4. Four
5. Five
"""
    hierarchy = _hierarchy([
        {
            "type": "PART", "identifier": "I", "title": "PRELIMINARY",
            "opening_text": "Short title", "start_page": 2,
            "children": [{
                "type": "SECTION", "identifier": "1.", "title": "Short title",
                "opening_text": "This Act may be cited", "start_page": 2,
                "children": [],
            }],
        },
        {
            "type": "SCHEDULE", "identifier": "FIRST SCHEDULE", "title": "",
            "opening_text": "One", "start_page": 3, "children": [],
        },
    ])

    assert validate_source_hierarchy_completeness(
        hierarchy,
        document_text,
        page_count=3,
    ) == ()


# Purpose: avoid treating numbered business-report lines as legal sections.
def test_non_legal_document_is_not_subject_to_legal_completeness_gate():
    document_text = """[[PAGE_LABEL: 1]]
1. Revenue
2. Costs
3. Profit
4. Risks
5. Outlook
"""
    hierarchy = _hierarchy([{
        "type": "HEADING",
        "identifier": "",
        "title": "Annual report",
        "opening_text": "Revenue increased this year",
        "start_page": 1,
        "children": [],
    }])

    assert validate_source_hierarchy_completeness(
        hierarchy,
        document_text,
        page_count=1,
    ) == ()
