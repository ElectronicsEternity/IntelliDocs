from app.services.rag.service import RagService
from app.rag.generator import Generator
from app.rag.retriever import Retriever
from types import SimpleNamespace
import pytest


class FakeRetriever:
    def __init__(self):
        self.owner_id = None

    def retrieve(self, *, question, owner_id, top_k):
        self.owner_id = owner_id
        return [{
            "document_id": "doc-a", "document_title": "A", "metadata": {},
            "text": "owned context",
        }]


class FakeGenerator:
    last_usage = {"prompt_tokens": 4, "completion_tokens": 2}

    def generate(self, question, chunks):
        return "answer"


class FakeConversations:
    def ensure(self, user_id, conversation_id):
        return "conversation-a"

    def add_message(self, *args, **kwargs):
        pass


class FakeUsage:
    def ensure_ai_budget_available(self, user_id):
        pass

    def record(self, *args, **kwargs):
        pass


class LimitReachedUsage(FakeUsage):
    def ensure_ai_budget_available(self, user_id):
        from fastapi import HTTPException
        raise HTTPException(429, "Your Trial plan usage allowance has been reached.")


def test_rag_retrieval_uses_authenticated_owner_only():
    retriever = FakeRetriever()
    service = RagService(
        retriever=retriever,
        generator=FakeGenerator(),
        conversations=FakeConversations(),
        usage=FakeUsage(),
    )
    result = service.chat(
        question="question", user_id="user-a", conversation_id=None, top_k=5,
    )
    assert retriever.owner_id == "user-a"
    assert result["sources"][0]["document_id"] == "doc-a"


def test_rag_usage_allowance_is_checked_before_retrieval():
    retriever = FakeRetriever()
    service = RagService(
        retriever=retriever,
        generator=FakeGenerator(),
        conversations=FakeConversations(),
        usage=LimitReachedUsage(),
    )

    import pytest
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as error:
        service.chat(question="question", user_id="user-a", conversation_id=None, top_k=5)

    assert error.value.status_code == 429
    assert retriever.owner_id is None


def test_retriever_scopes_every_search_path_to_owner():
    owners = []

    class Embedder:
        def generate_embedding(self, question):
            return [0.1]

    class Store:
        def list_document_routing_candidates(self, *, owner_id, embedding):
            owners.append(owner_id)
            return [{
                "document_id": "00000000-0000-0000-0000-000000000001",
                "document_title": "Question guide",
                "filename": "question-guide.pdf",
                "topics": ["Question"],
                "description_similarity": 0.9,
            }]

        def search(self, *, owner_id, embedding, top_k, document_id, excluded_chunk_ids):
            owners.append(owner_id)
            return []

        def search_node_hierarchy(self, *, owner_id, embedding, top_k, document_id, excluded_chunk_ids):
            owners.append(owner_id)
            return []

        def search_exact_identifier(
            self, *, owner_id, query, embedding, top_k, document_id
        ):
            owners.append(owner_id)
            return []

    Retriever(Embedder(), Store()).retrieve("question", "user-a")
    assert owners == ["user-a", "user-a", "user-a", "user-a"]


def test_exact_identifier_subtree_precedes_semantic_supplements():
    retriever = object.__new__(Retriever)
    vector_results = [
        {"chunk_id": "outside", "text": "Similar section", "similarity": 0.9},
        {"chunk_id": "child-2", "text": "Second child", "similarity": 0.8},
    ]
    node_results = [
        {"chunk_id": "outside", "text": "Similar section", "similarity": 0.9},
    ]
    # Exact-identifier retrieval returns the anchor subtree in hierarchy order.
    identifier_results = [
        {"chunk_id": "anchor", "text": "Section 6", "similarity": 0.6},
        {"chunk_id": "child-1", "text": "Subsection 1", "similarity": 0.5},
        {"chunk_id": "child-2", "text": "Subsection 2", "similarity": 0.8},
    ]

    results = retriever._combine_results(
        vector_results,
        node_results,
        identifier_results,
        top_k=4,
    )

    assert [result["chunk_id"] for result in results] == [
        "anchor", "child-1", "child-2", "outside",
    ]


def test_fallback_preserves_complete_sections_in_multiple_documents():
    # Exercise retrieval end to end with a saved-vector substitute: no API call.
    class Embedder:
        def generate_embedding(self, question):
            return [0.1]

    class Store:
        def list_document_routing_candidates(self, **kwargs):
            return [
                {"document_id": doc, "document_title": doc, "filename": doc,
                 "topics": [], "description_similarity": 0.0}
                for doc in ["a", "b"]
            ]

        def search(self, **kwargs):
            assert kwargs["top_k"] == 10
            return []

        def search_node_hierarchy(self, **kwargs):
            return []

        def search_exact_identifier(self, **kwargs):
            assert kwargs["top_k"] is None
            doc = kwargs["document_id"]
            return [
                {"chunk_id": f"{doc}-{i}", "document_id": doc,
                 "text": f"Section child {i}", "similarity": 0.1}
                for i in range(7)
            ]

    results = Retriever(Embedder(), Store()).retrieve("Section 6", "user-a", top_k=10)
    assert len(results) == 14
    assert [item["chunk_id"] for item in results] == [
        f"{doc}-{i}" for doc in ["a", "b"] for i in range(7)
    ]
    assert Retriever._round_robin([[{"chunk_id": "extra"}]], 0) == []


@pytest.mark.parametrize("sizes,fallback,expected", [
    ([30], False, [20]),
    ([30], True, [20]),
    ([30, 3], False, [17, 3]),
    ([30, 30], False, [10, 10]),
])
def test_documents_share_one_allowance(sizes, fallback, expected):
    # Fake embeddings and stores test selection without any paid API request.
    class Embedder:
        def generate_embedding(self, question):
            return [0.1]

    class Store:
        def search_exact_identifier(self, **kwargs):
            return []

        def search(self, **kwargs):
            assert kwargs["top_k"] == 20
            doc = kwargs["document_id"]
            return [
                {"chunk_id": f"{doc}-{i}", "document_id": doc,
                 "text": str(i), "similarity": 0.9}
                for i in range(min(sizes[int(doc)], kwargs["top_k"]))
            ]

        def search_node_hierarchy(self, **kwargs):
            assert kwargs["top_k"] == 20
            return []

    retriever = Retriever(Embedder(), Store())
    retriever.document_router = SimpleNamespace(select=lambda **kwargs: (
        [{"document_id": str(i), "combined_score": 0.9}
         for i in range(len(sizes))], fallback,
    ))
    results = retriever.retrieve("rates", "user-a", top_k=20)
    assert len(results) == 20
    assert len({item["chunk_id"] for item in results}) == 20
    assert [sum(item["document_id"] == str(i) for item in results)
            for i in range(len(sizes))] == expected


def test_section_children_consume_one_local_selection_slot():
    # Six child chunks plus nine supplements are ten units, not fifteen units.
    retriever = object.__new__(Retriever)
    exact = [
        {"chunk_id": f"section-{i}", "document_id": "a",
         "exact_anchor_id": "root-6", "text": str(i), "similarity": 0.5}
        for i in range(6)
    ]
    semantic = [
        {"chunk_id": f"extra-{i}", "text": str(i), "similarity": 0.8}
        for i in range(10)
    ]
    result = retriever._combine_results(semantic, [], exact, top_k=10)
    assert len(result) == 15
    assert [item["chunk_id"] for item in result[6:]] == [f"extra-{i}" for i in range(9)]


def test_exact_bundle_is_resolved_before_both_semantic_searches():
    calls = []

    class Embedder:
        def generate_embedding(self, question):
            return [0.1]

    class Store:
        def list_document_routing_candidates(self, **kwargs):
            return [{"document_id": "a", "document_title": "a", "filename": "a",
                     "topics": [], "description_similarity": 0.9}]

        def search_exact_identifier(self, **kwargs):
            calls.append("exact")
            return [{"chunk_id": chunk_id, "document_id": "a", "text": chunk_id,
                     "exact_anchor_id": "root", "similarity": 0.5}
                    for chunk_id in ["root", "child", "child"]]

        def search(self, **kwargs):
            calls.append("chunk_vector")
            assert kwargs["excluded_chunk_ids"] == ["root", "child"]
            return [{"chunk_id": "additional", "document_id": "a",
                     "text": "additional", "similarity": 0.8}]

        def search_node_hierarchy(self, **kwargs):
            calls.append("node_vector")
            assert kwargs["excluded_chunk_ids"] == ["root", "child"]
            return []

    results = Retriever(Embedder(), Store()).retrieve("Section 6", "user-a")
    assert calls == ["exact", "chunk_vector", "node_vector"]
    assert [item["chunk_id"] for item in results] == ["root", "child", "additional"]


@pytest.mark.parametrize("method", ["search", "search_node_hierarchy"])
def test_sql_excludes_exact_chunks_before_search_limits(method):
    from app.storage.postgres_vector_store import PostgresVectorStore

    class Probe:
        def cursor(self): return self
        def execute(self, statement, parameters):
            self.statement, self.parameters = statement, parameters
        def fetchall(self): return []
        def close(self): pass

    probe = Probe()
    store = PostgresVectorStore.__new__(PostgresVectorStore)
    store.connection = probe
    excluded = ["00000000-0000-0000-0000-000000000001"]
    getattr(store, method)(owner_id="owner", embedding=[0.1], top_k=10,
                          document_id=None, excluded_chunk_ids=excluded)
    assert probe.statement.count("%s") == len(probe.parameters)
    assert "d.user_id = %s" in probe.statement
    assert probe.statement.index("ANY(%s::uuid[])") < probe.statement.index("LIMIT %s")
    assert probe.parameters.count(excluded) == (2 if method == "search_node_hierarchy" else 1)


def test_distinct_section_roots_consume_distinct_slots():
    # Sections 4 and 6 stay separate even within one document.
    retriever = object.__new__(Retriever)
    exact = [
        {"chunk_id": f"{root}-{i}", "document_id": "a",
         "exact_anchor_id": root, "text": str(i), "similarity": 0.5}
        for root in ["root-4", "root-6"] for i in range(3)
    ]
    semantic = [
        {"chunk_id": f"extra-{i}", "text": str(i), "similarity": 0.8}
        for i in range(4)
    ]
    result = retriever._combine_results(semantic, [], exact, top_k=3)
    assert len(result) == 7
    assert result[-1]["chunk_id"] == "extra-0"


@pytest.mark.parametrize("unit_limit", [10, 20])
def test_cross_document_limit_counts_section_units_not_child_chunks(unit_limit):
    class Embedder:
        def generate_embedding(self, question):
            return [0.1]

    class Store:
        def list_document_routing_candidates(self, **kwargs):
            return [
                {"document_id": doc, "document_title": doc, "filename": doc,
                 "topics": [], "description_similarity": 0.9}
                for doc in ["a", "b"]
            ]

        def search(self, **kwargs):
            doc = kwargs["document_id"]
            return [
                {"chunk_id": f"{doc}-extra-{i}", "document_id": doc,
                 "text": str(i), "similarity": 0.9}
                for i in range(10)
            ]

        def search_node_hierarchy(self, **kwargs):
            return []

        def search_exact_identifier(self, **kwargs):
            doc = kwargs["document_id"]
            return [
                {"chunk_id": f"{doc}-section-{i}", "document_id": doc,
                 "exact_anchor_id": "root-6", "text": str(i), "similarity": 0.5}
                for i in range(6)
            ]

    results = Retriever(Embedder(), Store()).retrieve("Section 6", "user-a", top_k=unit_limit)
    # Two six-chunk sections consume two units; remaining slots hold supplements.
    supplements_per_document = (unit_limit - 2) // 2
    assert len(results) == 12 + unit_limit - 2
    assert sum("exact_identifier" in item["match_types"] for item in results) == 12
    assert [item["chunk_id"] for item in results[12:]] == [
        f"{doc}-extra-{i}" for i in range(supplements_per_document) for doc in ["a", "b"]
    ]


def test_answer_prompt_requires_structured_markdown():
    captured = {}

    class Completions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                usage=None,
                choices=[SimpleNamespace(message=SimpleNamespace(content="Answer"))],
            )

    generator = Generator.__new__(Generator)
    generator.client = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))
    generator.last_usage = {}
    generator.generate(
        question="What are the rates?",
        chunks=[{"text": "RM57.69", "document_title": "Order"}],
    )

    prompt = captured["messages"][0]["content"]
    assert captured["model"] == "gpt-6.1-sol"
    assert captured["reasoning_effort"] == "medium"
    assert "Format the answer as clean Markdown" in prompt
    assert "Put every bullet or numbered item on its own line" in prompt
    assert "Use nested bullets for subcategories" in prompt
    assert "An applicability clause is a clause that expressly states" in prompt
    assert "use it as the controlling scope" in prompt


def test_chat_deduplicates_chunks_and_displays_at_most_five_sources():
    class DuplicateRetriever:
        def retrieve(self, **_kwargs):
            chunks = [
                {
                    "chunk_id": f"chunk-{index}",
                    "document_id": "doc-a",
                    "document_title": "Order",
                    "metadata": {},
                    "text": f"Evidence {index}",
                }
                for index in range(6)
            ]
            return [chunks[0], chunks[0].copy(), *chunks[1:]]

    class CapturingGenerator(FakeGenerator):
        def __init__(self):
            self.chunks = []

        def generate(self, question, chunks):
            self.chunks = chunks
            return "answer"

    generator = CapturingGenerator()
    service = RagService(
        retriever=DuplicateRetriever(),
        generator=generator,
        conversations=FakeConversations(),
        usage=FakeUsage(),
    )

    result = service.chat(
        question="question", user_id="user-a", conversation_id=None, top_k=10,
    )

    assert len(generator.chunks) == 6
    assert len(result["sources"]) == 5
    assert [source["text"] for source in result["sources"]] == [
        "Evidence 0", "Evidence 1", "Evidence 2", "Evidence 3", "Evidence 4",
    ]


def test_table_source_exposes_structured_cells_for_display():
    source = RagService._build_source({
        "document_id": "doc-a",
        "document_title": "Order",
        "content_type": "table",
        "text": "Row 1: columns 1-1: Area",
        "metadata": {
            "table_number": 3,
            "page_numbers": [4, 5],
            "fields": [{
                "value": "Area",
                "row_start": 1,
                "row_end": 2,
                "column_start": 1,
                "column_end": 1,
            }],
        },
    })

    assert source["page_number"] == 4
    assert source["table"]["table_number"] == 3
    assert source["table"]["fields"][0]["value"] == "Area"
