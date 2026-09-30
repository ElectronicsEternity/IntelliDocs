from app.rag.document_router import DocumentRouter, derive_topics


class Store:
    def __init__(self, candidates):
        self.candidates = candidates

    def list_document_routing_candidates(self, *, owner_id, embedding):
        assert owner_id == "user-a"
        assert embedding == [0.1]
        return self.candidates


def candidate(document_id, title, filename, similarity=0.0, topics=None):
    return {
        "document_id": document_id,
        "document_title": title,
        "filename": filename,
        "description_similarity": similarity,
        "topics": topics or [],
    }


def test_topics_are_derived_from_titles_without_duplicate_model_output():
    hierarchy = {
        "title": "",
        "children": [
            {"title": "Interpretation", "children": []},
            {"title": "  Interpretation  ", "children": []},
            {"title": "Minimum wages", "children": []},
        ],
    }
    assert derive_topics(hierarchy) == ["Interpretation", "Minimum wages"]


def test_exact_filename_match_guarantees_document_selection():
    router = DocumentRouter(Store([
        candidate("a", "Employment Act", "akta-kerja.pdf", 0.0),
        candidate("b", "Other", "other.pdf", 0.99),
    ]))
    selected, fallback = router.select(
        question="What is stated in akta kerja pdf?",
        owner_id="user-a",
        embedding=[0.1],
    )
    assert not fallback
    assert [item["document_id"] for item in selected] == ["a"]


def test_no_confident_document_uses_broad_library_fallback():
    router = DocumentRouter(Store([
        candidate("a", "Alpha", "alpha.pdf"),
        candidate("b", "Beta", "beta.pdf"),
    ]))
    selected, fallback = router.select(
        question="unrelated material",
        owner_id="user-a",
        embedding=[0.1],
    )
    assert fallback
    assert {item["document_id"] for item in selected} == {"a", "b"}


def test_named_document_remains_primary_without_hiding_relevant_documents():
    router = DocumentRouter(Store([
        candidate("a", "Employment Act", "employment-act.pdf", 0.1),
        candidate(
            "b", "Minimum Wages Order", "wages.pdf", 0.95,
            topics=["Wage requirements"],
        ),
    ]))
    selected, fallback = router.select(
        question="Compare Employment Act wage requirements",
        owner_id="user-a",
        embedding=[0.1],
    )
    assert not fallback
    assert [item["document_id"] for item in selected] == ["a", "b"]
