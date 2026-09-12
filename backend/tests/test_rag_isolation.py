from app.services.rag.service import RagService
from app.rag.retriever import Retriever


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
    def record(self, *args, **kwargs):
        pass


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
