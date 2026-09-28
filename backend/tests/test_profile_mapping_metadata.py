from unittest.mock import Mock

from app.indexing.document_profile_validator import DocumentProfileValidator
from app.indexing.hierarchy_importer import HierarchyImporter


def hierarchy():
    return {
        "type": "DOCUMENT",
        "language": "en",
        "identifier": "",
        "title": "",
        "opening_text": None,
        "start_page": 1,
        "page_coverage": [
            {"page_label": 1, "classification": "new_nodes_start_here"},
            {"page_label": 2, "classification": "no_new_nodes_start_here"},
        ],
        "children": [
            {
                "type": "SECTION",
                "identifier": "1.",
                "title": "Alpha",
                "opening_text": "Alpha",
                "start_page": 1,
                "children": [],
            }
        ],
    }


def test_mapping_metadata_requires_complete_exact_page_coverage():
    result = DocumentProfileValidator().validate(
        hierarchy(),
        expected_language="en",
        expected_page_count=2,
        require_mapping_metadata=True,
    )
    assert result.is_valid


def test_mapping_metadata_rejects_missing_page_and_backward_sibling():
    profile = hierarchy()
    profile["page_coverage"] = profile["page_coverage"][:1]
    profile["children"].append(
        {
            "type": "SECTION",
            "identifier": "2.",
            "title": "Beta",
            "opening_text": "Beta",
            "start_page": 0,
            "children": [],
        }
    )
    result = DocumentProfileValidator().validate(
        profile,
        expected_page_count=2,
        require_mapping_metadata=True,
    )
    assert not result.is_valid
    assert any("page_coverage" in error for error in result.errors)
    assert any("outside PAGE_LABEL" in error for error in result.errors)


def test_importer_returns_page_hints_and_opening_text_by_generated_node_id():
    importer = HierarchyImporter(db=object())
    importer.repository = Mock(owner_id=None)

    metadata = importer.import_hierarchy(
        document_id="document-a",
        hierarchy=hierarchy(),
        owner_id="user-a",
    )

    assert sorted(metadata["page_hints"].values()) == [1, 1]
    assert list(metadata["opening_texts"].values()) == ["Alpha"]
