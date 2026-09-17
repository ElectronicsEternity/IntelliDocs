from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from app.api.dependencies import get_usage_tracker
from app.main import app
from app.services.usage.plans import get_plan_limits
from app.services.usage.tracker import UsageTracker


class FakeUsageTracker:
    def summary(self, user_id: str) -> dict:
        now = datetime.now(timezone.utc)
        return {
            "plan_code": "trial",
            "plan_name": "Trial",
            "period_start": now,
            "period_end": now,
            "documents": {"used": 2, "limit": 25},
            "storage_bytes": {"used": 1024, "limit": 52428800},
            "pages_processed": {"used": 10, "limit": 500},
            "questions": {"used": 4, "limit": 100},
        }


def test_usage_requires_authentication(client):
    assert client.get("/usage").status_code == 401


def test_usage_returns_authenticated_users_plan(user_a_client):
    app.dependency_overrides[get_usage_tracker] = lambda: FakeUsageTracker()

    response = user_a_client.get("/usage")

    assert response.status_code == 200
    assert response.json()["plan_code"] == "trial"
    assert response.json()["documents"] == {"used": 2, "limit": 25}


class InMemoryUsageTracker(UsageTracker):
    def __init__(self, monthly: dict[str, int] | None = None):
        self.monthly = monthly or {}

    def plan_for_user(self, user_id: str):
        return get_plan_limits("trial")

    def monthly_quantity(self, user_id: str, event_type: str) -> int:
        return self.monthly.get(event_type, 0)


def test_trial_question_limit_is_enforced(monkeypatch):
    monkeypatch.setattr("app.config.settings.TRIAL_MAX_QUESTIONS_PER_MONTH", 2)
    tracker = InMemoryUsageTracker({"rag_question": 2})

    with pytest.raises(HTTPException) as error:
        tracker.ensure_question_allowed("user-a")

    assert error.value.status_code == 429
    assert "Trial plan" in str(error.value.detail)


def test_trial_page_limit_checks_the_incoming_document(monkeypatch):
    monkeypatch.setattr("app.config.settings.TRIAL_MAX_PAGES_PER_MONTH", 10)
    tracker = InMemoryUsageTracker({"pages_processed": 8})

    with pytest.raises(HTTPException) as error:
        tracker.ensure_processing_allowed("user-a", 3)

    assert error.value.status_code == 429
    assert "page-processing limit" in str(error.value.detail)
