from app.services.rag.service import RagService
from app.rag.generator import Generator
from app.rag.retriever import Retriever
from types import SimpleNamespace


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
    def ensure_question_allowed(self, user_id):
        pass

    def record(self, *args, **kwargs):
        pass


class LimitReachedUsage(FakeUsage):
    def ensure_question_allowed(self, user_id):
        from fastapi import HTTPException
        raise HTTPException(429, "Your Trial plan monthly question limit has been reached.")


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


def test_rag_question_limit_is_checked_before_retrieval():
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
        def search(self, *, owner_id, embedding, top_k):
            owners.append(owner_id)
            return []

        def search_node_hierarchy(self, *, owner_id, embedding, top_k):
            owners.append(owner_id)
            return []

        def search_exact_identifier(self, *, owner_id, query, embedding, top_k):
            owners.append(owner_id)
            return []

    Retriever(Embedder(), Store()).retrieve("question", "user-a")
    assert owners == ["user-a", "user-a", "user-a"]


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
    assert "Format the answer as clean Markdown" in prompt
    assert "Put every bullet or numbered item on its own line" in prompt
    assert "Use nested bullets for subcategories" in prompt


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
