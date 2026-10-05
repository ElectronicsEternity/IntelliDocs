"""Allowance safety tests: provider calls are mocked, never paid."""
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace as NS
import os
import uuid

import pytest
from fastapi import HTTPException

from app.services.usage import ai_usage, reservations
from app.services.usage.ai_usage import ai_usage_context, estimate_request_cost, tracked_ai_call
from app.services.usage.plans import get_plan_limits


@pytest.fixture
def guarded(monkeypatch):
    events = []
    monkeypatch.setattr("app.services.usage.tracker.UsageTracker.ensure_ai_budget_available", lambda *_: None)
    monkeypatch.setattr(reservations, "reserve", lambda user, amount: events.append(("reserve", user, amount)) or "hold-id")
    monkeypatch.setattr(reservations, "finish", lambda hold, row, **kwargs: events.append(("finish", hold, row, kwargs)))
    monkeypatch.setattr(ai_usage, "_insert", lambda _: pytest.fail("Reserved requests must settle atomically."))
    return events


def test_hold_precedes_call_and_actual_cost_replaces_it(guarded):
    def call():
        guarded.append(("call",))
        return NS(usage=NS(input_tokens=10, output_tokens=20), model="gpt-6.1-sol")
    with ai_usage_context(user_id="user", enforce_budget=True):
        tracked_ai_call(call, activity="chat", model="gpt-6.1-sol", budget_estimate=lambda: Decimal("1"))
    assert [event[0] for event in guarded] == ["reserve", "call", "finish"]
    assert guarded[-1][2]["estimated_cost_usd"] == Decimal("0.00022")


def test_exhausted_allowance_never_sends_or_records_provider_call(monkeypatch, guarded):
    def reject(*_):
        raise HTTPException(429, "exhausted")
    monkeypatch.setattr(reservations, "reserve", reject)
    with ai_usage_context(user_id="user", enforce_budget=True), pytest.raises(HTTPException):
        tracked_ai_call(lambda: pytest.fail("Provider must not run"), activity="chat",
            model="gpt-6.1-sol", budget_estimate=lambda: Decimal("1"))
    assert guarded == []


def test_missing_estimate_fails_closed(guarded):
    with ai_usage_context(user_id="user", enforce_budget=True), pytest.raises(ValueError, match="estimate missing"):
        tracked_ai_call(lambda: pytest.fail("Provider must not run"), activity="chat", model="gpt-6.1-sol")
    assert guarded == []


@pytest.mark.parametrize("status,rejected", [(400,True),(401,True),(403,True),(404,True),(422,True),(429,True),(500,False),(None,False)])
def test_only_definite_rejections_release_hold(guarded, status, rejected):
    error = RuntimeError("provider failure")
    error.status_code = status
    def call():
        raise error
    with ai_usage_context(user_id="user", enforce_budget=True), pytest.raises(RuntimeError):
        tracked_ai_call(call, activity="chat", model="gpt-6.1-sol", budget_estimate=lambda: Decimal("1"))
    assert guarded[-1][3]["rejected"] is rejected


def test_missing_usage_is_retained_for_review(guarded):
    with ai_usage_context(user_id="user", enforce_budget=True):
        tracked_ai_call(lambda: NS(usage=None), activity="chat", model="gpt-6.1-sol", budget_estimate=lambda: Decimal("1"))
    assert guarded[-1][2]["status"] == "usage_missing"
    assert not guarded[-1][3]["rejected"]


def test_settlement_failure_does_not_repeat_request(monkeypatch, guarded):
    calls = []
    def fail(*_, **__):
        raise RuntimeError("database unavailable")
    monkeypatch.setattr(reservations, "finish", fail)
    with ai_usage_context(user_id="user", enforce_budget=True):
        tracked_ai_call(lambda: calls.append(1) or NS(usage=None), activity="chat",
            model="gpt-6.1-sol", budget_estimate=lambda: Decimal("1"))
    assert calls == [1]


def test_embedding_estimate_counts_literal_special_tokens():
    amount = estimate_request_cost("text-embedding-3-small", {"input": ["hello", "<|endoftext|>"]})
    assert amount > 0


def test_text_estimate_requires_output_bound_and_unknown_pricing_fails():
    with pytest.raises(ValueError, match="bounded"):
        estimate_request_cost("gpt-6.1-sol", {"input": "hello"})
    with pytest.raises(ValueError, match="pricing"):
        estimate_request_cost("unknown", {"input": "hello", "max_output_tokens": 1})


def test_pdf_estimate_uses_full_input_count_and_long_context(monkeypatch):
    monkeypatch.setattr(ai_usage.settings, "AI_LONG_CONTEXT_TOKEN_THRESHOLD", 100)
    counts = []
    request = {"model": "gpt-6.1-sol", "input": [{"type": "input_file", "file_data": "pdf"}],
        "text": {"format": {"type": "json_schema"}}, "max_output_tokens": 10}
    client = NS(responses=NS(input_tokens=NS(count=lambda **kwargs: counts.append(kwargs) or NS(input_tokens=101))))
    amount = estimate_request_cost("gpt-6.1-sol", request, client=client)
    assert amount == Decimal("0.000554")
    assert counts == [{key:value for key,value in request.items() if key != "max_output_tokens"}]


class Cursor:
    def __init__(self, rows):
        self.rows = iter(rows)
        self.queries = []
    def __enter__(self):
        return self
    def __exit__(self, *_):
        pass
    def execute(self, sql, args=None):
        self.queries.append((sql, args))
    def fetchone(self):
        return next(self.rows)


def install_connection(monkeypatch, rows):
    cur = Cursor(rows)
    connection = NS(cursor=lambda: cur)
    @contextmanager
    def get_connection():
        yield connection
    monkeypatch.setattr(reservations, "get_connection", get_connection)
    return cur, connection


def test_reserve_checks_committed_and_held_cost_under_same_lock(monkeypatch):
    cur, conn = install_connection(monkeypatch, [(Decimal("0.9"),)])
    now = datetime.now(timezone.utc)
    plan = replace(get_plan_limits("trial"), ai_budget_usd=Decimal("1"))
    def period(_, user, *, connection):
        assert connection is conn
        return plan, now-timedelta(days=1), now+timedelta(days=1)
    monkeypatch.setattr(reservations.UsageTracker, "period_for_user", period)
    with pytest.raises(HTTPException):
        reservations.reserve("user", Decimal("0.2"))
    assert "pg_advisory_xact_lock" in cur.queries[0][0]
    assert "state IN ('held','uncertain')" in cur.queries[1][0]
    assert not any("INSERT" in sql for sql, _ in cur.queries)


@pytest.mark.parametrize("status,cost,rejected,expected", [
    ("completed",Decimal("0.2"),False,"settled"),
    ("usage_missing",None,False,"uncertain"),
    ("api_error",None,True,"released"),
    ("api_error",None,False,"uncertain"),
])
def test_settlement_uses_original_period_and_atomic_state(monkeypatch, status, cost, rejected, expected):
    created = datetime.now(timezone.utc)-timedelta(hours=1)
    cur, _ = install_connection(monkeypatch, [("user",),("held",created)])
    reservations.finish("hold", {"user_id":"user", "status":status, "estimated_cost_usd":cost}, rejected=rejected)
    assert "pg_advisory_xact_lock" in cur.queries[1][0]
    assert created in cur.queries[3][1]
    assert cur.queries[4][1] == (expected,"hold","hold")


@pytest.mark.parametrize("state", ["settled", "released", "uncertain"])
def test_repeated_finish_does_not_double_charge(monkeypatch, state):
    cur, _ = install_connection(monkeypatch, [("user",),(state,datetime.now(timezone.utc))])
    reservations.finish("hold", {"user_id":"user"})
    assert len(cur.queries) == 3


@pytest.mark.skipif(os.getenv("TEST_AI_RESERVATIONS_DB") != "1", reason="Explicit opt-in for isolated database QA records")
def test_real_postgres_concurrent_holds_and_settlement(monkeypatch):
    # Use a unique QA owner; delete only this test's temporary accounting records.
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from app.database.connection import get_connection
    user = "reservation-qa-" + str(uuid.uuid4())
    start = datetime.now(timezone.utc)-timedelta(hours=1)
    end = start+timedelta(days=1)
    plan = replace(get_plan_limits("trial"), ai_budget_usd=Decimal("1"))
    monkeypatch.setattr(reservations.UsageTracker, "period_for_user", lambda *_, **__: (plan,start,end))
    barrier = Barrier(2)
    def attempt():
        barrier.wait(timeout=10)
        try:
            return reservations.reserve(user, Decimal("0.7"))
        except HTTPException as exc:
            assert exc.status_code == 429
            return None
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            holds = list(pool.map(lambda _: attempt(), range(2)))
        assert sum(hold is not None for hold in holds) == 1
        hold = next(hold for hold in holds if hold)
        record = ai_usage.build_record(NS(usage=NS(input_tokens=10,output_tokens=20)),
            activity="chat", model="gpt-6.1-sol", user_id=user)
        reservations.finish(hold, record)
        reservations.finish(hold, record)
        # Actual tiny cost replaces 0.7; the released capacity can be reserved again.
        second = reservations.reserve(user, Decimal("0.9"))
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM ai_usage WHERE user_id=%s", (user,))
            assert cur.fetchone()[0] == 1
            cur.execute("SELECT state FROM ai_usage_reservations WHERE id=%s", (second,))
            assert cur.fetchone()[0] == "held"
            cur.execute("SELECT relrowsecurity FROM pg_class WHERE oid='ai_usage_reservations'::regclass")
            assert cur.fetchone()[0]
            cur.execute("SELECT has_table_privilege('authenticated','ai_usage_reservations','SELECT')")
            assert not cur.fetchone()[0]
    finally:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM ai_usage_reservations WHERE user_id=%s", (user,))
            cur.execute("DELETE FROM ai_usage WHERE user_id=%s", (user,))
