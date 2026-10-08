"""Check the real assembled answer request without paid model or storage calls.

These are prompt-contract regressions, not proof of live model compliance.
"""
from copy import deepcopy
from types import SimpleNamespace as NS

import pytest

from app.rag import generator as module


@pytest.fixture
def assembled_request(monkeypatch):
    requests, captures = [], []

    class Capture:
        def __init__(self, **kwargs):
            captures.append(kwargs)

        def finish(self, **kwargs):
            pass

    def create(**kwargs):
        requests.append(kwargs)
        return NS(usage=None, choices=[NS(message=NS(content="stubbed answer"))])

    monkeypatch.setattr(module, "AnswerDebugCapture", Capture)
    monkeypatch.setattr(module, "tracked_ai_call", lambda call, **kwargs: call())
    instance = module.Generator.__new__(module.Generator)
    instance.client = NS(chat=NS(completions=NS(create=create)))

    def assemble(question, chunks):
        original = deepcopy(chunks)
        assert instance.generate(question, chunks) == "stubbed answer"
        assert chunks == original
        assert captures[-1]["request"] == requests[-1]
        assert captures[-1]["prompt_version"] == module.ANSWER_PROMPT_VERSION
        return requests[-1]["messages"][0]["content"]

    return assemble


def evidence(doc="doc-a", title="Perintah Gaji Minimum", text="Kadar RM1,500."):
    return {"chunk_id": doc + "-chunk", "document_id": doc, "node_id": doc + "-node",
            "document_title": title, "node_type": "SECTION", "identifier": "4.",
            "text": text, "metadata": {"page_numbers": [3]}}


@pytest.mark.parametrize("question", [
    "Adakah elaun boleh dikira bagi memenuhi gaji minimum?",
    "Can allowances count towards the minimum wage?",
    "Jawab dalam Bahasa Melayu: Can allowances count towards the minimum wage?",
])
@pytest.mark.parametrize("chunks", [[], [evidence()], [
    evidence(), evidence("doc-b", "Employment Act", "Working-hour conditions."),
]])
def test_language_and_missing_evidence_contract(assembled_request, question, chunks):
    prompt = assembled_request(question, chunks)
    assert question in prompt
    assert "language explicitly requested by the user" in prompt
    assert "otherwise use\nthe language of the question" in prompt
    assert "even when the evidence is in another language" in prompt
    assert "Do not insert an unsolicited English\nfallback into a Malay answer" in prompt
    assert "Saya tidak menemui maklumat yang mencukupi" in prompt
    assert "I could not find sufficient information in the attached document(s)" in prompt
    assert '"I could not find the answer in the provided document."' not in prompt
    assert "Adapt singular/plural" in prompt
    assert "Do not claim that information is absent everywhere" in prompt
    assert "Do not claim an\nexhaustive or broader document search" in prompt
    assert "both use the general evidence limitation" in prompt
    assert "Never invent\na source title or citation" in prompt
    for chunk in chunks:
        assert chunk["text"] in prompt
        assert chunk["document_title"] in prompt
    if chunks:
        assert "Identifier: 4." in prompt and "Pages: 3" in prompt


def test_partial_answers_keep_evidence_and_citations(assembled_request):
    prompt = assembled_request("Compare wages and overtime rules.", [evidence()])
    assert "When the context supports the answer, answer with supporting citations" in prompt
    assert "explain the supported findings\nwith citations and identify the unanswered part" in prompt
    assert "do not discard useful evidence" in prompt
    assert "apply the notice only to the unanswered part" in prompt
    assert "Original document titles, legal identifiers and verbatim source quotations" in prompt
    assert "Never rename a SUBSECTION as a SECTION" in prompt


def test_prompt_version_marks_new_instructions():
    assert module.ANSWER_PROMPT_VERSION == "language-aware-evidence-fallback-v4"
