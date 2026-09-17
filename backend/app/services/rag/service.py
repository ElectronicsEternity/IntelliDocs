import uuid

from fastapi import HTTPException, status

from app.config import settings
from app.database.connection import get_connection
from app.rag.embedder import Embedder
from app.rag.generator import Generator
from app.rag.retriever import Retriever
from app.storage.postgres_vector_store import PostgresVectorStore
from app.services.usage.tracker import UsageTracker
from app.services.usage.ai_usage import ai_usage_context


class ConversationRepository:
    def ensure(self, user_id: str, conversation_id: str | None) -> str:
        with get_connection() as conn, conn.cursor() as cur:
            if conversation_id:
                cur.execute(
                    "SELECT id FROM conversations WHERE id = %s AND user_id = %s",
                    (conversation_id, user_id),
                )
                if cur.fetchone() is None:
                    raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found.")
                return conversation_id
            new_id = str(uuid.uuid4())
            cur.execute(
                "INSERT INTO conversations (id, user_id, created_at, updated_at) VALUES (%s, %s, NOW(), NOW())",
                (new_id, user_id),
            )
            return new_id

    def add_message(
        self,
        conversation_id: str,
        user_id: str,
        role: str,
        content: str,
        *,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
    ) -> None:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO messages (
                    id, conversation_id, user_id, role, content,
                    prompt_tokens, completion_tokens, created_at
                )
                SELECT %s, %s, %s, %s, %s, %s, %s, NOW()
                WHERE EXISTS (
                    SELECT 1 FROM conversations WHERE id = %s AND user_id = %s
                )
                """,
                (
                    str(uuid.uuid4()), conversation_id, user_id, role, content,
                    prompt_tokens, completion_tokens, conversation_id, user_id,
                ),
            )


class RagService:
    MAX_DISPLAY_SOURCES = 5

    def __init__(
        self,
        retriever: Retriever | None = None,
        generator: Generator | None = None,
        conversations: ConversationRepository | None = None,
        usage: UsageTracker | None = None,
        vector_store: PostgresVectorStore | None = None,
    ) -> None:
        self.vector_store = vector_store
        if retriever is None:
            self.vector_store = self.vector_store or PostgresVectorStore()
            retriever = Retriever(Embedder(), self.vector_store)
        self.retriever = retriever
        self.generator = generator or Generator()
        self.conversations = conversations or ConversationRepository()
        self.usage = usage or UsageTracker()

    def chat(self, *, question: str, user_id: str, conversation_id: str | None, top_k: int | None) -> dict:
        self.usage.ensure_question_allowed(user_id)
        conversation_id = self.conversations.ensure(user_id, conversation_id)
        with ai_usage_context(user_id=user_id, conversation_id=conversation_id):
            chunks = self._unique_chunks(
                self.retriever.retrieve(
                    question=question,
                    owner_id=user_id,
                    top_k=top_k or settings.RAG_TOP_K,
                )
            )
            answer = self.generator.generate(question=question, chunks=chunks)
        usage = getattr(self.generator, "last_usage", {}) or {}
        self.conversations.add_message(conversation_id, user_id, "user", question)
        self.conversations.add_message(
            conversation_id, user_id, "assistant", answer,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
        )
        self.usage.record(
            user_id, "rag_question",
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
        )
        sources = [self._build_source(item) for item in chunks[:self.MAX_DISPLAY_SOURCES]]
        return {"conversation_id": conversation_id, "answer": answer, "sources": sources}

    @staticmethod
    def _build_source(item: dict) -> dict:
        metadata = item.get("metadata") or {}
        content_type = item.get("content_type") or "text"
        table = None
        if content_type == "table":
            table = {
                "table_number": metadata.get("table_number", 0),
                "page_numbers": list(metadata.get("page_numbers") or []),
                "fields": [
                    {
                        "value": str(field.get("value") or ""),
                        "row_start": int(field["row_start"]),
                        "row_end": int(field["row_end"]),
                        "column_start": int(field["column_start"]),
                        "column_end": int(field["column_end"]),
                    }
                    for field in metadata.get("fields") or []
                ],
            }
        page_numbers = metadata.get("page_numbers") or []
        return {
            "document_id": item["document_id"],
            "document_title": item.get("document_title"),
            "page_number": metadata.get("start_page") or (page_numbers[0] if page_numbers else None),
            "text": item["text"],
            "content_type": content_type,
            "table": table,
        }

    @staticmethod
    def _unique_chunks(chunks: list[dict]) -> list[dict]:
        """Keep the highest-ranked copy of each retrieved chunk."""
        unique: list[dict] = []
        seen_ids: set[str] = set()
        seen_content: set[tuple[str, str]] = set()

        for chunk in chunks:
            chunk_id = str(chunk.get("chunk_id") or "")
            content_key = (
                str(chunk.get("document_id") or ""),
                " ".join(str(chunk.get("text") or "").split()).casefold(),
            )
            if (chunk_id and chunk_id in seen_ids) or content_key in seen_content:
                continue
            if chunk_id:
                seen_ids.add(chunk_id)
            seen_content.add(content_key)
            unique.append(chunk)

        return unique

    def close(self) -> None:
        if self.vector_store is not None:
            self.vector_store.close()
