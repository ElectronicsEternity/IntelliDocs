from fastapi import HTTPException, status
from psycopg.rows import dict_row

from app.database.connection import get_connection
from app.services.usage.plans import PlanLimits, get_plan_limits


class UsageTracker:
    def plan_for_user(self, user_id: str) -> PlanLimits:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO user_accounts (user_id, plan_code, created_at, updated_at)
                VALUES (%s, 'trial', NOW(), NOW())
                ON CONFLICT (user_id) DO NOTHING
                """,
                (user_id,),
            )
            cur.execute("SELECT plan_code FROM user_accounts WHERE user_id = %s", (user_id,))
            row = cur.fetchone()
        return get_plan_limits(str(row[0]) if row else "trial")

    def monthly_quantity(self, user_id: str, event_type: str) -> int:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT COALESCE(SUM(quantity), 0)
                FROM usage_records
                WHERE user_id = %s AND event_type = %s
                  AND created_at >= date_trunc('month', NOW())
                  AND created_at < date_trunc('month', NOW()) + interval '1 month'
                """,
                (user_id, event_type),
            )
            row = cur.fetchone()
            return int(row[0]) if row else 0

    def ensure_upload_allowed(
        self,
        user_id: str,
        *,
        document_count: int,
        storage_bytes: int,
        incoming_bytes: int,
    ) -> None:
        plan = self.plan_for_user(user_id)
        if document_count >= plan.documents:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                f"Your {plan.name} plan document limit has been reached.",
            )
        if storage_bytes + incoming_bytes > plan.storage_bytes:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                f"Your {plan.name} plan storage limit would be exceeded.",
            )

    def ensure_processing_allowed(self, user_id: str, page_count: int) -> None:
        plan = self.plan_for_user(user_id)
        pages_used = self.monthly_quantity(user_id, "pages_processed")
        if pages_used + page_count > plan.pages_per_month:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                f"Your {plan.name} plan monthly page-processing limit would be exceeded.",
            )

    def ensure_question_allowed(self, user_id: str) -> None:
        plan = self.plan_for_user(user_id)
        questions_used = self.monthly_quantity(user_id, "rag_question")
        if questions_used >= plan.questions_per_month:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                f"Your {plan.name} plan monthly question limit has been reached.",
            )

    def summary(self, user_id: str) -> dict:
        plan = self.plan_for_user(user_id)
        with get_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT COUNT(*)::bigint AS documents,
                       COALESCE(SUM(file_size), 0)::bigint AS storage_bytes
                FROM documents WHERE user_id = %s
                """,
                (user_id,),
            )
            totals = dict(cur.fetchone() or {})
            cur.execute(
                """
                SELECT
                    date_trunc('month', NOW()) AS period_start,
                    date_trunc('month', NOW()) + interval '1 month' AS period_end,
                    COALESCE(SUM(quantity) FILTER (
                        WHERE event_type = 'pages_processed'
                    ), 0)::bigint AS pages_processed,
                    COALESCE(SUM(quantity) FILTER (
                        WHERE event_type = 'rag_question'
                    ), 0)::bigint AS questions
                FROM usage_records
                WHERE user_id = %s
                  AND created_at >= date_trunc('month', NOW())
                  AND created_at < date_trunc('month', NOW()) + interval '1 month'
                """,
                (user_id,),
            )
            monthly = dict(cur.fetchone() or {})

        return {
            "plan_code": plan.code,
            "plan_name": plan.name,
            "period_start": monthly["period_start"],
            "period_end": monthly["period_end"],
            "documents": {"used": int(totals.get("documents", 0)), "limit": plan.documents},
            "storage_bytes": {"used": int(totals.get("storage_bytes", 0)), "limit": plan.storage_bytes},
            "pages_processed": {
                "used": int(monthly.get("pages_processed", 0)),
                "limit": plan.pages_per_month,
            },
            "questions": {
                "used": int(monthly.get("questions", 0)),
                "limit": plan.questions_per_month,
            },
        }

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
