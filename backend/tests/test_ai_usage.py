from decimal import Decimal
from types import SimpleNamespace as NS

import pytest

from app.services.usage.ai_usage import ai_usage_context, build_record, tracked_ai_call


def response(model="gpt-5-mini", **usage):
    return NS(model=model, id="response-1", _request_id="request-1", usage=NS(**usage))


def test_chat_cost_and_cached_reasoning_are_not_double_counted():
    row = build_record(
        response(prompt_tokens=8000, completion_tokens=2000,
                 prompt_tokens_details=NS(cached_tokens=1000),
                 completion_tokens_details=NS(reasoning_tokens=500)),
        activity="chat", model="gpt-5-mini", user_id="user-a",
    )
    assert row["estimated_cost_usd"] == Decimal("0.005775")
    assert row["total_tokens"] == 10000
    assert row["reasoning_tokens"] == 500


def test_profiling_and_embedding_costs():
    profile = build_record(
        response("gpt-5", input_tokens=60000, output_tokens=10000),
        activity="profiling", model="gpt-5", user_id="user-a", attempt=2,
    )
    embedding = build_record(
        response("text-embedding-3-small", prompt_tokens=200000, total_tokens=200000),
        activity="chunk_embedding", model="text-embedding-3-small", user_id="user-a",
    )
    assert profile["estimated_cost_usd"] == Decimal("0.175")
    assert profile["attempt"] == 2
    assert embedding["estimated_cost_usd"] == Decimal("0.004")
    assert embedding["output_tokens"] == 0


def test_missing_usage_and_unknown_model_do_not_claim_zero_cost():
    missing = build_record(NS(usage=None), activity="chat", model="gpt-5-mini", user_id="a")
    unknown = build_record(response("unknown", input_tokens=1, output_tokens=2),
                           activity="chat", model="unknown", user_id="a")
    assert missing["input_tokens"] is None
    assert missing["estimated_cost_usd"] is None
    assert missing["status"] == "usage_missing"
    assert unknown["estimated_cost_usd"] is None


def test_context_restores_owner_and_errors_have_unknown_usage(monkeypatch):
    rows = []
    monkeypatch.setattr("app.services.usage.ai_usage._insert", rows.append)
    with ai_usage_context(user_id="a", conversation_id="conversation-a"):
        with ai_usage_context(user_id="b"):
            tracked_ai_call(lambda: response(input_tokens=1, output_tokens=2), activity="chat", model="gpt-5-mini")
        tracked_ai_call(lambda: response(input_tokens=1, output_tokens=2), activity="chat", model="gpt-5-mini")
        def fail():
            raise RuntimeError("sensitive internal message")
        with pytest.raises(RuntimeError):
            tracked_ai_call(fail, activity="chat", model="gpt-5-mini")
    assert [row["user_id"] for row in rows] == ["b", "a", "a"]
    assert rows[-1]["status"] == "api_error"
    assert rows[-1]["estimated_cost_usd"] is None
    assert rows[-1]["error_type"] == "RuntimeError"
    assert "sensitive" not in str(rows)


def test_real_embedding_adapter_logs_provider_usage(monkeypatch):
    from app.rag.embedder import Embedder
    rows = []
    monkeypatch.setattr("app.services.usage.ai_usage._insert", rows.append)
    embedder = Embedder.__new__(Embedder)
    result = response("text-embedding-3-small", prompt_tokens=12, total_tokens=12)
    result.data = [NS(embedding=[0.1])]
    embedder.client = NS(embeddings=NS(create=lambda **_kwargs: result))
    with ai_usage_context(user_id="user-a", conversation_id="conversation-a", embedding_activity="query_embedding"):
        assert embedder.generate_embedding("question") == [0.1]
    assert rows[0]["activity"] == "query_embedding"
    assert rows[0]["conversation_id"] == "conversation-a"


def test_profiler_logs_each_validation_attempt(monkeypatch):
    from app.indexing.document_profiler import DocumentProfiler
    rows = []
    monkeypatch.setattr("app.services.usage.ai_usage._insert", rows.append)
    profiler = DocumentProfiler.__new__(DocumentProfiler)
    result = response("gpt-5", input_tokens=100, output_tokens=20)
    result.output_text = "{}"
    profiler.client = NS(responses=NS(create=lambda **_kwargs: result))
    validations = iter([NS(errors=("retry",)), NS(errors=())])
    profiler.validator = NS(validate=lambda **_kwargs: next(validations))
    profiler._build_prompt = lambda **_kwargs: "prompt"
    profiler._build_retry_prompt = lambda **_kwargs: "retry prompt"
    profiler._save_attempt = lambda **_kwargs: None
    profiler._save_accepted_profile = lambda **_kwargs: None
    assert profiler.generate_hierarchy("text", "en", "doc-a", "user-a") == {}
    assert [row["attempt"] for row in rows] == [1, 2]
    assert all(row["document_id"] == "doc-a" for row in rows)


def test_chat_generator_logs_tokens_before_answer_is_returned(monkeypatch):
    from app.rag.generator import Generator
    rows = []
    monkeypatch.setattr("app.services.usage.ai_usage._insert", rows.append)
    generator = Generator.__new__(Generator)
    result = response(prompt_tokens=8000, completion_tokens=2000)
    result.choices = [NS(message=NS(content="Answer"))]
    generator.client = NS(chat=NS(completions=NS(create=lambda **_kwargs: result)))
    with ai_usage_context(user_id="user-a", conversation_id="conversation-a"):
        assert generator.generate("Question", [{"text": "Evidence", "document_title": "Order"}]) == "Answer"
    assert rows[0]["activity"] == "chat"
    assert rows[0]["estimated_cost_usd"] == Decimal("0.006")
    assert generator.last_usage["prompt_tokens"] == 8000


def test_analytics_failure_does_not_repeat_paid_call(monkeypatch):
    def reject(_record):
        raise RuntimeError("database unavailable")
    monkeypatch.setattr("app.services.usage.ai_usage._insert", reject)
    calls = []
    def call():
        calls.append(1)
        return response(input_tokens=1, output_tokens=2)
    with ai_usage_context(user_id="user-a"):
        result = tracked_ai_call(call, activity="chat", model="gpt-5-mini")
    assert result is not None
    assert len(calls) == 1
