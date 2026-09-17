from contextlib import contextmanager
from contextvars import ContextVar
from decimal import Decimal
import logging
import uuid

from app.config import settings
from app.database.connection import get_connection

logger = logging.getLogger(__name__)
_context: ContextVar[dict] = ContextVar("ai_usage_context", default={})


@contextmanager
def ai_usage_context(**values):
    token = _context.set({**_context.get(), **values})
    try:
        yield
    finally:
        _context.reset(token)


def _get(value, key, default=None):
    return value.get(key, default) if isinstance(value, dict) else getattr(value, key, default)


def _rates(model: str):
    if model == "gpt-5-mini" or model.startswith("gpt-5-mini-"):
        values = (settings.AI_GPT5_MINI_INPUT_RATE, settings.AI_GPT5_MINI_CACHED_INPUT_RATE, settings.AI_GPT5_MINI_OUTPUT_RATE)
    elif model == "gpt-5" or model.startswith("gpt-5-202"):
        values = (settings.AI_GPT5_INPUT_RATE, settings.AI_GPT5_CACHED_INPUT_RATE, settings.AI_GPT5_OUTPUT_RATE)
    elif model == "text-embedding-3-small":
        values = (settings.AI_EMBEDDING_INPUT_RATE, settings.AI_EMBEDDING_INPUT_RATE, 0)
    else:
        return None
    return tuple(Decimal(str(value)) for value in values)


def build_record(response, *, activity, model, user_id, document_id=None, conversation_id=None, attempt=1, error=None):
    usage = _get(response, "usage")
    reported_model = _get(response, "model") or model
    input_tokens = _get(usage, "input_tokens", _get(usage, "prompt_tokens"))
    output_tokens = _get(usage, "output_tokens", _get(usage, "completion_tokens"))
    if usage is not None and reported_model == "text-embedding-3-small":
        output_tokens = 0
    input_details = _get(usage, "input_tokens_details", _get(usage, "prompt_tokens_details"))
    output_details = _get(usage, "output_tokens_details", _get(usage, "completion_tokens_details"))
    cached = _get(input_details, "cached_tokens", 0) if usage is not None else None
    reasoning = _get(output_details, "reasoning_tokens", 0) if usage is not None else None
    total = _get(usage, "total_tokens")
    if total is None and input_tokens is not None and output_tokens is not None:
        total = input_tokens + output_tokens
    rates = _rates(reported_model)
    cost = None
    if rates is not None and input_tokens is not None and output_tokens is not None:
        # Cached input is a subset of input; reasoning is already in output.
        cost = (Decimal(input_tokens - cached) * rates[0] + Decimal(cached) * rates[1] + Decimal(output_tokens) * rates[2]) / Decimal(1_000_000)
    return {
        "id": str(uuid.uuid4()), "user_id": user_id,
        "document_id": document_id, "conversation_id": conversation_id,
        "activity": activity, "model": reported_model,
        "request_id": _get(response, "_request_id") or _get(error, "request_id"),
        "response_id": _get(response, "id"), "attempt": attempt,
        "status": "api_error" if error else ("completed" if usage is not None else "usage_missing"),
        "input_tokens": input_tokens, "cached_input_tokens": cached,
        "output_tokens": output_tokens, "reasoning_tokens": reasoning, "total_tokens": total,
        "input_rate_usd": rates[0] if rates else None,
        "cached_input_rate_usd": rates[1] if rates else None,
        "output_rate_usd": rates[2] if rates else None,
        "estimated_cost_usd": cost,
        "error_type": type(error).__name__ if error else None,
    }


def _insert(record):
    columns = list(record)
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            f"INSERT INTO ai_usage ({', '.join(columns)}) VALUES ({', '.join(['%s'] * len(columns))})",
            tuple(record[column] for column in columns),
        )


def tracked_ai_call(call, *, activity, model, user_id=None, document_id=None, attempt=1):
    context = _context.get()
    if activity == "embedding":
        activity = context.get("embedding_activity", activity)
    owner = user_id or context.get("user_id")
    response = None
    error = None
    try:
        response = call()
        return response
    except Exception as exc:
        error = exc
        raise
    finally:
        if owner:
            try:
                record = build_record(
                    response, activity=activity, model=model, user_id=owner,
                    document_id=document_id or context.get("document_id"),
                    conversation_id=context.get("conversation_id"), attempt=attempt, error=error,
                )
                _insert(record)
            except Exception:
                # Never repeat a paid request just because analytics storage failed.
                logger.exception("AI usage logging failed for activity %s", activity)
