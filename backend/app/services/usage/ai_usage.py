from contextlib import contextmanager
from contextvars import ContextVar
from decimal import Decimal
import logging
import json
import uuid

from app.config import settings
from app.database.connection import get_connection

logger = logging.getLogger(__name__)
_context: ContextVar[dict] = ContextVar("ai_usage_context", default={})


def get_ai_usage_context() -> dict:
    # Return a copy so diagnostics can correlate requests without mutating
    # the authenticated user/conversation context used by cost tracking.
    return _context.get().copy()


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
    # Accept dated response model names as well as the configured alias.
    if model == "gpt-6.1-sol" or model.startswith("gpt-6.1-sol-"):
        values = (settings.AI_GPT61_SOL_INPUT_RATE, settings.AI_GPT61_SOL_CACHED_INPUT_RATE, settings.AI_GPT61_SOL_OUTPUT_RATE)
    elif model == "gpt-5.6-sol" or model.startswith("gpt-5.6-sol-"):
        values = (settings.AI_GPT56_SOL_INPUT_RATE, settings.AI_GPT56_SOL_CACHED_INPUT_RATE, settings.AI_GPT56_SOL_OUTPUT_RATE)
    elif model == "gpt-5.6-terra" or model.startswith("gpt-5.6-terra-"):
        values = (settings.AI_GPT56_TERRA_INPUT_RATE, settings.AI_GPT56_TERRA_CACHED_INPUT_RATE, settings.AI_GPT56_TERRA_OUTPUT_RATE)
    elif model == "gpt-5.4-mini" or model.startswith("gpt-5.4-mini-"):
        values = (settings.AI_GPT54_MINI_INPUT_RATE, settings.AI_GPT54_MINI_CACHED_INPUT_RATE, settings.AI_GPT54_MINI_OUTPUT_RATE)
    elif model == "gpt-5-mini" or model.startswith("gpt-5-mini-"):
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
        if input_tokens > settings.AI_LONG_CONTEXT_TOKEN_THRESHOLD and reported_model.startswith(("gpt-5.6-", "gpt-6.1-sol")):
            # Both families charge 2x input/cached input and 1.5x output
            # for the entire request above the long-context threshold.
            rates = (rates[0] * 2, rates[1] * 2, rates[2] * Decimal("1.5"))
        # Cached input is a subset of input; reasoning is already in output.
        cost = (Decimal(input_tokens - cached) * rates[0] + Decimal(cached) * rates[1] + Decimal(output_tokens) * rates[2]) / Decimal(1_000_000)
    return {
        "id": str(uuid.uuid4()), "user_id": user_id,
        "document_id": document_id, "conversation_id": conversation_id,
        "activity": activity, "model": reported_model,
        "request_id": _get(response, "_request_id") or _get(error, "request_id"),
        # Non-retry calls may pass None explicitly. Store the first-attempt
        # value required by the database so the blocked call remains visible.
        "response_id": _get(response, "id"), "attempt": attempt or 1,
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


def estimate_request_cost(model, request, *, client=None):
    """Conservative input + maximum output cost, using no cached-input discount."""
    rates = _rates(model)
    if rates is None or any(rate < 0 for rate in rates):
        raise ValueError("AI model pricing must be configured before spending allowance.")
    if model == "text-embedding-3-small":
        import tiktoken
        encoding = tiktoken.get_encoding("cl100k_base")
        # Literal user text must not be interpreted as tokenizer control tokens.
        inputs = request["input"]
        inputs = [inputs] if isinstance(inputs, str) else inputs
        input_tokens = sum(len(encoding.encode(text, disallowed_special=())) for text in inputs)
        output_tokens = 0
    elif '"input_file"' in json.dumps(request):
        # A PDF's bytes alone cannot predict its rendered-image token cost.
        # Ask the provider's counting endpoint, not its answer-generation endpoint.
        if client is None:
            raise ValueError("PDF token counting requires the configured provider client.")
        count_request = {key: request[key] for key in ("model", "input", "text", "reasoning") if key in request}
        input_tokens = client.responses.input_tokens.count(**count_request).input_tokens
        output_tokens = request["max_output_tokens"]
    else:
        # UTF-8 bytes bound text tokens conservatively; include framing/schema overhead.
        input_tokens = len(json.dumps(request, ensure_ascii=False).encode("utf-8")) + 1024
        output_tokens = request.get("max_output_tokens", request.get("max_completion_tokens"))
    if not isinstance(input_tokens, int) or input_tokens < 0 or not isinstance(output_tokens, int) or output_tokens < 0:
        raise ValueError("A bounded AI request is required before reserving allowance.")
    if input_tokens > settings.AI_LONG_CONTEXT_TOKEN_THRESHOLD and model.startswith(("gpt-5.6-", "gpt-6.1-sol")):
        rates = (rates[0] * 2, rates[1] * 2, rates[2] * Decimal("1.5"))
    return (Decimal(input_tokens) * rates[0] + Decimal(output_tokens) * rates[2]) / Decimal(1_000_000)


def tracked_ai_call(call, *, activity, model, user_id=None, document_id=None, attempt=1, budget_estimate=None):
    context = _context.get()
    if activity == "embedding":
        activity = context.get("embedding_activity", activity)
    owner = user_id or context.get("user_id")
    response = None
    error = None
    reservation_id = None
    invoked = False
    try:
        if owner and context.get("enforce_budget"):
            # Import locally to keep the usage logger independent at import time.
            from app.services.usage.tracker import UsageTracker
            UsageTracker().ensure_ai_budget_available(owner)
            from app.services.usage.reservations import reserve
            if budget_estimate is None:
                raise ValueError("AI allowance estimate missing; request was not sent.")
            reservation_id = reserve(owner, budget_estimate())
        invoked = True
        response = call()
        return response
    except Exception as exc:
        error = exc
        raise
    finally:
        if owner and invoked:
            try:
                record = build_record(
                    response, activity=activity, model=model, user_id=owner,
                    document_id=document_id or context.get("document_id"),
                    conversation_id=context.get("conversation_id"), attempt=attempt, error=error,
                )
                if reservation_id:
                    from app.services.usage.reservations import finish
                    # Explicit provider rejection is safe to release. Timeouts,
                    # connection errors and server errors retain an uncertain hold.
                    rejected = _get(error, "status_code") in (400, 401, 403, 404, 422, 429)
                    finish(reservation_id, record, rejected=rejected)
                else:
                    _insert(record)
            except Exception:
                # Never repeat a paid request just because analytics storage failed.
                logger.exception("AI usage logging failed for activity %s", activity)
