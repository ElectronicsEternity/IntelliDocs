"""Atomic, per-account allowance holds surrounding each paid provider request."""
from datetime import datetime, timezone
from decimal import Decimal, ROUND_CEILING
import uuid

from fastapi import HTTPException

from app.database.connection import get_connection
from app.services.usage.tracker import UsageTracker


def reserve(user_id: str, amount: Decimal) -> str:
    if not amount.is_finite() or amount < 0:
        raise ValueError("Invalid AI allowance reservation.")
    # Round upward to the database precision, never down toward free allowance.
    amount = amount.quantize(Decimal("0.0000000001"), rounding=ROUND_CEILING)
    reservation_id = str(uuid.uuid4())
    with get_connection() as conn, conn.cursor() as cur:
        # Match billing's lock key so renewals and spending cannot race each other.
        cur.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (user_id,))
        plan, start, end = UsageTracker().period_for_user(user_id, connection=conn)
        if not start <= datetime.now(timezone.utc) < end:
            raise HTTPException(429, "Your usage period is not active. Please check your subscription.")
        cur.execute("""SELECT
            (SELECT COALESCE(SUM(estimated_cost_usd),0) FROM ai_usage
                WHERE user_id=%s AND status='completed' AND created_at >= %s AND created_at < %s)
            + (SELECT COALESCE(SUM(reserved_usd),0) FROM ai_usage_reservations
                WHERE user_id=%s AND period_start=%s AND period_end=%s
                    AND state IN ('held','uncertain'))""",
            (user_id, start, end, user_id, start, end))
        committed = Decimal(str(cur.fetchone()[0]))
        if committed + amount > plan.ai_budget_usd:
            raise HTTPException(429,
                "Not enough available allowance to safely start this AI request. "
                "Other requests may still be processing. Try a narrower request or retry after they finish.")
        cur.execute("""INSERT INTO ai_usage_reservations
            (id,user_id,period_start,period_end,reserved_usd) VALUES (%s,%s,%s,%s,%s)""",
            (reservation_id, user_id, start, end, amount))
    # Commit the hold before calling the provider; do not keep any database lock open.
    return reservation_id


def finish(reservation_id: str, record: dict, *, rejected: bool = False) -> None:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT user_id FROM ai_usage_reservations WHERE id=%s", (reservation_id,))
        owner = cur.fetchone()
        if not owner:
            raise RuntimeError("AI allowance reservation not found.")
        cur.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (owner[0],))
        cur.execute("SELECT state,created_at FROM ai_usage_reservations WHERE id=%s FOR UPDATE", (reservation_id,))
        state, created_at = cur.fetchone()
        if state != 'held':
            return  # A repeated completion must not insert the same usage twice.
        record = {**record, "id": reservation_id, "created_at": created_at}
        if record["user_id"] != owner[0]:
            raise ValueError("AI usage owner does not match its allowance hold.")
        columns = list(record)
        # Both writes commit together: actual cost replaces the hold, not adds to it.
        cur.execute(
            f"INSERT INTO ai_usage ({', '.join(columns)}) VALUES ({', '.join(['%s'] * len(columns))}) "
            "ON CONFLICT (id) DO NOTHING",
            tuple(record[column] for column in columns),
        )
        known_cost = record["status"] == "completed" and record["estimated_cost_usd"] is not None
        next_state = "settled" if known_cost else "released" if rejected else "uncertain"
        cur.execute("""UPDATE ai_usage_reservations SET state=%s,usage_id=%s,updated_at=now()
            WHERE id=%s""", (next_state, reservation_id, reservation_id))
        # Unknown outcomes have no expiry: a timeout does not prove the provider was unpaid.
