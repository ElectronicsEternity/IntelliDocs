from app.indexing.document_profile_validator import DocumentProfileValidator


def test_routing_description_is_required_when_requested():
    hierarchy = {
        "type": "DOCUMENT",
        "language": "en",
        "identifier": "",
        "title": "",
        "opening_text": None,
        "children": [{
            "type": "HEADING",
            "identifier": "",
            "title": "Content",
            "opening_text": "Opening content text",
            "children": [],
        }],
    }
    result = DocumentProfileValidator().validate(
        hierarchy,
        require_routing_metadata=True,
    )
    assert any("document_description" in error for error in result.errors)


def test_profiler_prompt_requests_description_but_not_separate_topics():
    from app.indexing.document_profiler import DocumentProfiler

    prompt = DocumentProfiler.__new__(DocumentProfiler)._build_prompt(
        document_text="[[PAGE_LABEL: 1]]\nContent",
        document_language="en",
        page_count=1,
    )
    assert "document_description" in prompt
    assert "250-350 word description" in prompt
    assert '"topics"' not in prompt
