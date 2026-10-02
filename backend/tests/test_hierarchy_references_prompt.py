"""Keep reference metadata in the real hierarchy prompt without reverse guesses."""
from app.indexing.document_profiler import DocumentProfiler
from app.indexing.hierarchy_prompt_rules import REFERENCE_RULES
from app.indexing.document_profile_validator import DocumentProfileValidator


def test_main_prompt_requests_node_level_internal_references():
    prompt = DocumentProfiler._build_prompt(None, "Sample source", "English", 1)
    assert REFERENCE_RULES in prompt
    assert "- references" in prompt
    assert '"references": []' in prompt
    assert '"identifier":"60A","sub_identifier":"(3)"' in prompt
    assert "Do not invent reverse references" in prompt
    assert "references to other Acts" in prompt
    assert "deepest actual hierarchy node" in prompt


def test_reference_contract_accepts_old_profiles_and_rejects_invalid_fields():
    tree = {"type": "DOCUMENT", "identifier": "", "title": "", "language": "English",
            "children": [{"type": "SECTION", "identifier": "60A.", "title": "Hours of work",
                          "children": []}]}
    validator = DocumentProfileValidator()
    assert validator.validate(tree).is_valid
    tree["children"][0]["references"] = [
        {"node_type": "SECTION", "identifier": "60D", "sub_identifier": "(1)"}]
    assert validator.validate(tree).is_valid
    tree["children"][0]["references"][0]["document_title"] = "Another Act"
    assert any("must contain exactly" in error for error in validator.validate(tree).errors)


def test_local_reference_matching_preserves_child_boundaries():
    # Import the experiment without running its paid-call entry point.
    from scripts.reference_hierarchy_experiment import child_key
    assert child_key("(1A)") != child_key("(1)(a)")
    assert child_key("(3) (b)") == child_key("(3)(b)")
