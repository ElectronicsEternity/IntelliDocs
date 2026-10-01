"""Keep the exact answer evidence in private local files during testing."""

from copy import deepcopy
from datetime import datetime
from decimal import Decimal
import json
import logging
from pathlib import Path
import traceback
from uuid import UUID, uuid4

from app.config import settings
from app.services.usage.ai_usage import build_record, get_ai_usage_context


LOGGER = logging.getLogger("uvicorn.error.rag_debug")


def _json_value(value):
    # Metadata and cost records can include database UUIDs and Decimal values.
    # Explicit conversion avoids accidentally recording arbitrary object reprs.
    if isinstance(value, (Decimal, UUID, Path)):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"Unsupported debug value type: {type(value).__name__}")


class AnswerDebugCapture:
    def __init__(self, *, question, chunks, request, prompt_version):
        self.path = None
        if not settings.RAG_DEBUG_CAPTURE_ENABLED:
            return

        timestamp = datetime.now().astimezone()
        self.capture_id = str(uuid4())
        context = get_ai_usage_context()
        folder = settings.RAG_DEBUG_CAPTURE_DIRECTORY / timestamp.strftime("%Y-%m-%d")
        self.path = folder / f"{timestamp:%Y%m%d-%H%M%S}_{self.capture_id}.json"
        # Freeze evidence before the API call, preserving text, IDs and ranking
        # in the same order as the actual answer-generation context.
        self.payload = {
            "schema_version": 1,
            "capture_id": self.capture_id,
            "started_at": timestamp.isoformat(),
            "user_id": context.get("user_id"),
            "conversation_id": context.get("conversation_id"),
            "prompt_version": prompt_version,
            "question": question,
            "chunks": deepcopy(chunks),
            "request": deepcopy(request),
            "status": "pending",
        }
        # If enabled capture cannot be saved, fail before spending on an answer
        # that would lack the evidence needed to troubleshoot it.
        try:
            self._write()
        except Exception as exc:
            LOGGER.error("rag_debug_save_failed capture_id=%s", self.capture_id)
            raise RuntimeError("Could not save the AI request debug file.") from exc
        LOGGER.info("rag_debug_request capture_id=%s path=%s", self.capture_id, self.path)

    def _write(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Replace one completed file atomically so readers never see half JSON.
        # UUID filenames isolate simultaneous requests, even within one second.
        temporary = self.path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(self.payload, ensure_ascii=False, indent=2, default=_json_value),
            encoding="utf-8",
        )
        temporary.replace(self.path)

    def finish(self, *, response=None, answer=None, error=None):
        if self.path is None:
            return
        try:
            self._finish(response=response, answer=answer, error=error)
        except Exception:
            # Preserve initial evidence and never repeat the paid API call if
            # response serialization or a final diagnostic write fails.
            LOGGER.error("rag_debug_finalize_failed capture_id=%s path=%s", self.capture_id, self.path)

    def _finish(self, *, response=None, answer=None, error=None):
        self.payload.update({
            "finished_at": datetime.now().astimezone().isoformat(),
            "status": "failed" if error else "completed",
            "answer": answer,
            # Use the same cost calculator as ai_usage. This snapshot is not a
            # second charge or an extra database usage record.
            "usage": build_record(
                response, activity="chat", model=self.payload["request"]["model"],
                user_id=self.payload["user_id"],
                conversation_id=self.payload["conversation_id"], error=error,
            ),
        })
        if response is not None and getattr(response, "choices", None):
            self.payload["finish_reason"] = getattr(response.choices[0], "finish_reason", None)
        if error is not None:
            # Capture useful stack locations without headers, credentials,
            # response bodies or exception messages that may echo API keys.
            self.payload["error"] = {
                "type": type(error).__name__,
                "status_code": getattr(error, "status_code", None),
                "frames": [
                    {"file": frame.filename, "line": frame.lineno, "function": frame.name}
                    for frame in traceback.extract_tb(error.__traceback__)
                ],
            }
        self._write()
