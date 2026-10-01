import json
from types import SimpleNamespace as NS

import pytest

from app.config import settings
from app.rag.debug_capture import AnswerDebugCapture
from app.rag.generator import Generator
from app.services.usage.ai_usage import ai_usage_context


@pytest.fixture
def capture_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "RAG_DEBUG_CAPTURE_ENABLED", True)
    monkeypatch.setattr(settings, "RAG_DEBUG_CAPTURE_DIRECTORY", tmp_path / "rag_debug")
    return settings.RAG_DEBUG_CAPTURE_DIRECTORY


def read_capture(folder):
    paths = list(folder.glob("*/*.json"))
    assert len(paths) == 1
    return paths[0], json.loads(paths[0].read_text(encoding="utf-8"))


def make_generator(monkeypatch, create):
    # Replace the paid call and analytics wrapper; exercise actual prompt
    # assembly and capture without accessing OpenAI or the database.
    monkeypatch.setattr("app.rag.generator.tracked_ai_call", lambda call, **kwargs: call())
    generator = Generator.__new__(Generator)
    generator.client = NS(chat=NS(completions=NS(create=create)))
    return generator


def test_exact_request_is_saved_before_call_and_completed_with_usage(capture_folder, monkeypatch):
    supplied = {}
    chunks = [
        {"chunk_id": "b", "document_title": "Order", "text": "First evidence", "identifier": "(3)"},
        {"chunk_id": "a", "document_title": "Order", "text": "Second evidence"},
    ]

    def create(**kwargs):
        _, pending = read_capture(capture_folder)
        assert pending["status"] == "pending"
        assert pending["request"] == kwargs
        supplied.update(kwargs)
        return NS(
            model="gpt-6.1-sol", id="response-a", _request_id="provider-a",
            usage=NS(prompt_tokens=8000, completion_tokens=2000,
                     prompt_tokens_details=NS(cached_tokens=1000),
                     completion_tokens_details=NS(reasoning_tokens=500)),
            choices=[NS(message=NS(content="Answer"), finish_reason="stop")],
        )

    generator = make_generator(monkeypatch, create)
    with ai_usage_context(user_id="user-a", conversation_id="conversation-a"):
        assert generator.generate("Who does Section 6 apply to?", chunks) == "Answer"
    path, saved = read_capture(capture_folder)
    assert saved["request"] == supplied
    assert saved["chunks"] == chunks
    assert saved["status"] == "completed"
    assert saved["user_id"] == "user-a"
    assert saved["conversation_id"] == "conversation-a"
    assert saved["answer"] == "Answer"
    assert saved["usage"]["estimated_cost_usd"] == "0.0341"
    assert saved["usage"]["request_id"] == "provider-a"
    assert saved["usage"]["reasoning_tokens"] == 500
    assert "Instructions:" in saved["request"]["messages"][0]["content"]
    assert saved["prompt_version"]
    assert path.parent.name == saved["started_at"][:10]
    assert not list(capture_folder.rglob("*.tmp"))


def test_api_failure_keeps_prompt_and_safe_error_details(capture_folder, monkeypatch):
    def create(**kwargs):
        raise ValueError("sensitive-key-must-not-be-saved")

    generator = make_generator(monkeypatch, create)
    with pytest.raises(ValueError):
        generator.generate("Question", [{"text": "Evidence"}])
    path, saved = read_capture(capture_folder)
    assert saved["status"] == "failed"
    assert saved["error"]["type"] == "ValueError"
    assert saved["error"]["frames"]
    assert saved["request"]["messages"]
    assert "sensitive-key" not in path.read_text(encoding="utf-8")


def test_initial_capture_failure_prevents_paid_call(capture_folder, monkeypatch):
    calls = []
    capture_folder.write_text("directory is unavailable", encoding="utf-8")
    generator = make_generator(monkeypatch, lambda **kwargs: calls.append(kwargs))
    with pytest.raises(RuntimeError, match="Could not save"):
        generator.generate("Question", [])
    assert calls == []


def test_final_capture_failure_preserves_pending_file_and_answer(capture_folder, monkeypatch):
    def create(**kwargs):
        def fail_write(self):
            raise OSError("disk full")
        monkeypatch.setattr(AnswerDebugCapture, "_write", fail_write)
        return NS(usage=None, choices=[NS(message=NS(content="Answer"))])

    generator = make_generator(monkeypatch, create)
    assert generator.generate("Question", []) == "Answer"
    _, saved = read_capture(capture_folder)
    assert saved["status"] == "pending"
    assert saved["request"]["messages"]


def test_disabled_capture_creates_no_files(capture_folder, monkeypatch):
    monkeypatch.setattr(settings, "RAG_DEBUG_CAPTURE_ENABLED", False)
    capture = AnswerDebugCapture(question="Q", chunks=[], request={}, prompt_version="v1")
    capture.finish(answer="A")
    assert not capture_folder.exists()


def test_each_question_has_its_own_file_and_frozen_chunks(capture_folder):
    chunks = [{"chunk_id": "a", "text": "original"}]
    args = dict(question="Q", chunks=chunks, request={"model": "gpt-6.1-sol"}, prompt_version="v1")
    first = AnswerDebugCapture(**args)
    second = AnswerDebugCapture(**args)
    chunks[0]["text"] = "changed"
    first.finish(answer="Answer")
    assert first.path != second.path
    assert len(list(capture_folder.glob("*/*.json"))) == 2
    assert json.loads(first.path.read_text(encoding="utf-8"))["chunks"][0]["text"] == "original"
