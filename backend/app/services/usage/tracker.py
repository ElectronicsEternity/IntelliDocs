from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import HTTPException, status
from psycopg.rows import dict_row

from app.config import settings
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

    def period_for_user(self, user_id: str) -> tuple[PlanLimits, datetime, datetime]:
        """Return the active billing/trial period without exposing its dollar value."""
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO user_accounts (user_id, plan_code, created_at, updated_at)
                VALUES (%s, 'trial', NOW(), NOW())
                ON CONFLICT (user_id) DO NOTHING
                """,
                (user_id,),
            )
            cur.execute(
                "SELECT plan_code, created_at FROM user_accounts WHERE user_id = %s",
                (user_id,),
            )
            row = cur.fetchone()
        plan = get_plan_limits(str(row[0]) if row else "trial")
        created_at = row[1] if row else datetime.now(timezone.utc)
        if plan.code == "trial":
            return plan, created_at, created_at + timedelta(days=settings.TRIAL_DURATION_DAYS)
        now = datetime.now(timezone.utc)
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
        return plan, start, end

    def ai_cost_used(self, user_id: str, period_start: datetime, period_end: datetime) -> Decimal:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT COALESCE(SUM(estimated_cost_usd), 0)
                FROM ai_usage
                WHERE user_id = %s AND status = 'completed'
                  AND created_at >= %s AND created_at < %s
                """,
                (user_id, period_start, period_end),
            )
            row = cur.fetchone()
        return Decimal(str(row[0] if row else 0))

    def ensure_ai_budget_available(self, user_id: str) -> None:
        plan, period_start, period_end = self.period_for_user(user_id)
        if datetime.now(timezone.utc) >= period_end:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "Your trial has ended. Upgrade to continue using AI processing and questions.",
            )
        if self.ai_cost_used(user_id, period_start, period_end) >= plan.ai_budget_usd:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                f"Your {plan.name} plan usage allowance has been reached.",
            )

    def monthly_quantity(self, user_id: str, event_type: str) -> int:
        _plan, period_start, period_end = self.period_for_user(user_id)
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT COALESCE(SUM(quantity), 0)
                FROM usage_records
                WHERE user_id = %s AND event_type = %s
                  AND created_at >= %s AND created_at < %s
                """,
                (user_id, event_type, period_start, period_end),
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

    def summary(self, user_id: str) -> dict:
        plan, period_start, period_end = self.period_for_user(user_id)
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
                    COALESCE(SUM(quantity) FILTER (
                        WHERE event_type = 'pages_processed'
                    ), 0)::bigint AS pages_processed
                FROM usage_records
                WHERE user_id = %s
                  AND created_at >= %s AND created_at < %s
                """,
                (user_id, period_start, period_end),
            )
            monthly = dict(cur.fetchone() or {})

        cost_used = self.ai_cost_used(user_id, period_start, period_end)
        used_percent = min(
            Decimal("100"),
            (cost_used / plan.ai_budget_usd * Decimal("100"))
            if plan.ai_budget_usd > 0 else Decimal("100"),
        )

        return {
            "plan_code": plan.code,
            "plan_name": plan.name,
            "period_start": period_start,
            "period_end": period_end,
            "documents": {"used": int(totals.get("documents", 0)), "limit": plan.documents},
            "storage_bytes": {"used": int(totals.get("storage_bytes", 0)), "limit": plan.storage_bytes},
            "pages_processed": {
                "used": int(monthly.get("pages_processed", 0)),
                "limit": plan.pages_per_month,
            },
            "ai_usage": {
                "used_percent": float(round(used_percent, 2)),
                "remaining_percent": float(round(max(Decimal("0"), Decimal("100") - used_percent), 2)),
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
