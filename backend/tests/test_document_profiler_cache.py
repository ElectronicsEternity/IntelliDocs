from types import SimpleNamespace as NS

from app.indexing.document_profile_validator import DocumentProfileValidator
from app.indexing.document_profiler import DocumentProfiler


# Purpose: provide one complete, validator-compatible non-legal hierarchy fixture.
def _valid_hierarchy():
    return {
        "type": "DOCUMENT",
        "language": "en",
        "identifier": "",
        "title": "",
        "opening_text": None,
        "start_page": 1,
        "page_coverage": [{
            "page_label": 1,
            "classification": "new_nodes_start_here",
        }],
        "children": [{
            "type": "HEADING",
            "identifier": "",
            "title": "Annual report",
            "opening_text": "Revenue increased during the reporting period",
            "start_page": 1,
            "children": [],
        }],
    }


# Purpose: prove a failed downstream retry does not repeat a paid hierarchy call.
def test_generate_hierarchy_reuses_matching_validated_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.indexing.document_profiler.DEFAULT_PROFILES_FOLDER",
        tmp_path,
    )
    profiler = DocumentProfiler.__new__(DocumentProfiler)
    profiler.validator = DocumentProfileValidator()
    profiler.client = NS(
        responses=NS(
            create=lambda **_kwargs: (_ for _ in ()).throw(
                AssertionError("OpenAI must not be called for a valid cache")
            )
        )
    )
    document_text = "[[PAGE_LABEL: 1]]\nAnnual report\nRevenue increased."
    prompt = profiler._build_prompt(
        document_text=document_text,
        document_language="en",
        page_count=1,
    )
    manifest = profiler._build_cache_manifest(
        document_text=document_text,
        document_language="en",
        page_count=1,
        prompt=prompt,
    )
    profiler._save_accepted_profile(
        owner_id="user-a",
        document_id="document-a",
        hierarchy=_valid_hierarchy(),
        cache_manifest=manifest,
    )

    result = profiler.generate_hierarchy(
        document_text=document_text,
        document_language="en",
        document_id="document-a",
        owner_id="user-a",
        page_count=1,
    )

    assert result == _valid_hierarchy()
