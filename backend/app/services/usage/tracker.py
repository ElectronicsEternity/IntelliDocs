from app.database.connection import get_connection


class UsageTracker:
    def record(
        self,
        user_id: str,
        event_type: str,
        *,
        quantity: int = 1,
        document_id: str | None = None,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
    ) -> None:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO usage_records (
                    user_id, event_type, quantity, document_id,
                    prompt_tokens, completion_tokens, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, NOW())
                """,
                (
                    user_id, event_type, quantity, document_id,
                    prompt_tokens, completion_tokens,
                ),
            )
