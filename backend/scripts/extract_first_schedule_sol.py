"""One-call Sol High semantic transcription experiment for Akta First Schedule."""

import base64
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from openai import OpenAI
from pypdf import PdfReader, PdfWriter

from app.config import settings
from app.services.usage.ai_usage import build_record


BASE = Path(__file__).resolve().parents[2] / "backups" / "2026-09-17"
SOURCE = BASE / "pdfs" / "Akta Kerja 1955 (Akta 265).pdf"
OUTPUT = BASE / "akta-first-schedule-gpt56-sol-high"
MODEL = "gpt-5.6-sol"
SOURCE_PAGES = [112, 113]

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "document_title", "table_title", "start_page", "end_page",
        "columns", "records", "transcription_notes",
    ],
    "properties": {
        "document_title": {"type": "string"},
        "table_title": {"type": "string"},
        "start_page": {"type": "integer"},
        "end_page": {"type": "integer"},
        "columns": {"type": "array", "items": {"type": "string"}},
        "records": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "record_id", "primary_text", "associated_provision",
                    "source_pages", "association_uncertainty",
                ],
                "properties": {
                    "record_id": {"type": "string"},
                    "primary_text": {"type": "string"},
                    "associated_provision": {"type": "string"},
                    "source_pages": {
                        "type": "array",
                        "items": {"type": "integer"},
                    },
                    "association_uncertainty": {"type": "string"},
                },
            },
        },
        "transcription_notes": {"type": "array", "items": {"type": "string"}},
    },
}

PROMPT = """Perform a lossless semantic transcription of the borderless table FIRST SCHEDULE.

The attached PDF contains only original physical PDF pages 112 and 113, in that
order. Use those ORIGINAL page numbers in the response.

This is a legal document. Do not summarize, paraphrase, translate, correct, or
silently infer content. Preserve printed wording, identifiers, punctuation,
numbers, and cross-page continuations.

Interpret the table as logical employee records:
- record_id must preserve the full printed hierarchy, for example `2(4)`, not
  merely `(4)`.
- primary_text contains the complete employee description for that logical
  record. Keep nested clauses such as (a), (b), and (c) with their governing
  record when they continue onto the next page.
- associated_provision contains only the right-column text that is visually
  associated with that exact record.
- If the right column is genuinely blank for a record, return an empty string.
- Never carry a right-column value forward or backward merely because nearby
  records share a parent paragraph.
- Complete the left-column record before associating the right-column value.
- source_pages lists every original physical page contributing to that record.
- association_uncertainty must be empty when the association is visually clear;
  otherwise explain the uncertainty without guessing.

Return every logical record once, in printed reading order. Before returning,
verify the alignment of every non-empty right-column value independently and
confirm that no printed table text was omitted.
"""


def write_json(path, value):
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )


def create_subset(path):
    reader = PdfReader(SOURCE)
    writer = PdfWriter()
    for page_number in SOURCE_PAGES:
        writer.add_page(reader.pages[page_number - 1])
    with path.open("wb") as handle:
        writer.write(handle)


def apply_sol_cost_rates(usage):
    if usage["input_tokens"] is None or usage["output_tokens"] is None:
        return usage
    long_context = usage["input_tokens"] > 272_000
    input_rate = Decimal("8") if long_context else Decimal("4")
    cached_rate = Decimal("0.8") if long_context else Decimal("0.4")
    output_rate = Decimal("30") if long_context else Decimal("20")
    uncached = usage["input_tokens"] - usage["cached_input_tokens"]
    usage.update(
        input_rate_usd=input_rate,
        cached_input_rate_usd=cached_rate,
        output_rate_usd=output_rate,
        estimated_cost_usd=(
            Decimal(uncached) * input_rate
            + Decimal(usage["cached_input_tokens"]) * cached_rate
            + Decimal(usage["output_tokens"]) * output_rate
        ) / Decimal(1_000_000),
    )
    return usage


def validate(result):
    errors = []
    if result.get("start_page") != 112 or result.get("end_page") != 113:
        errors.append("The returned original page range is not 112-113.")
    if len(result.get("columns", [])) != 2:
        errors.append("The table does not contain exactly two columns.")
    seen = set()
    for index, record in enumerate(result.get("records", []), 1):
        record_id = record.get("record_id")
        if not record_id or record_id in seen:
            errors.append(f"Record {index} has an empty or duplicate identifier.")
        seen.add(record_id)
        if not record.get("primary_text"):
            errors.append(f"Record {record_id!r} has no primary text.")
        pages = record.get("source_pages", [])
        if not pages or any(page not in SOURCE_PAGES for page in pages):
            errors.append(f"Record {record_id!r} has invalid source pages {pages}.")
    return errors


def main():
    OUTPUT.mkdir(exist_ok=True)
    subset = OUTPUT / "first-schedule-pages-112-113.pdf"
    create_subset(subset)
    metadata = {
        "source_pdf_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        "subset_pdf_sha256": hashlib.sha256(subset.read_bytes()).hexdigest(),
        "source_pages": SOURCE_PAGES,
        "model": MODEL,
        "reasoning_effort": "high",
        "prompt_sha256": hashlib.sha256(PROMPT.encode()).hexdigest(),
        "schema_sha256": hashlib.sha256(
            json.dumps(SCHEMA, sort_keys=True).encode()
        ).hexdigest(),
    }
    (OUTPUT / "prompt.txt").write_text(PROMPT, encoding="utf-8")
    response_path = OUTPUT / "response.json"
    if response_path.exists():
        saved = json.loads(response_path.read_text(encoding="utf-8"))
        if saved["metadata"] != metadata:
            raise RuntimeError("Cached response uses different experiment inputs.")
        print("Reusing saved Sol response; no paid call.", flush=True)
    else:
        marker = OUTPUT / "request-started.json"
        if marker.exists():
            raise RuntimeError("A prior request may have incurred cost; refusing retry.")
        if not settings.OPENAI_API_KEY:
            raise RuntimeError("OpenAI API key is unavailable.")
        write_json(marker, metadata)
        encoded = base64.b64encode(subset.read_bytes()).decode("ascii")
        client = OpenAI(api_key=settings.OPENAI_API_KEY, max_retries=0, timeout=1200)
        response = None
        error = None
        started = time.monotonic()
        try:
            response = client.responses.create(
                model=MODEL,
                reasoning={"effort": "high"},
                max_output_tokens=16000,
                input=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "input_file",
                            "filename": subset.name,
                            "file_data": f"data:application/pdf;base64,{encoded}",
                            "detail": "high",
                        },
                        {"type": "input_text", "text": PROMPT},
                    ],
                }],
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "first_schedule_semantic_transcription",
                        "strict": True,
                        "schema": SCHEMA,
                    }
                },
            )
        except Exception as exc:
            error = exc
        usage = apply_sol_cost_rates(build_record(
            response,
            activity="semantic_table_extraction_experiment",
            model=MODEL,
            user_id="offline-review",
            error=error,
        ))
        saved = {
            "metadata": metadata,
            "response": response.model_dump(mode="json") if response else None,
            "output_text": response.output_text if response else None,
            "usage": usage,
            "elapsed_seconds": time.monotonic() - started,
            "error_type": type(error).__name__ if error else None,
            "error_message": str(error) if error else None,
        }
        write_json(response_path, saved)
        if error:
            raise RuntimeError(f"Sol request failed: {type(error).__name__}: {error}")
    if not saved["response"] or saved["response"]["status"] != "completed":
        raise RuntimeError("Sol response was not completed.")
    result = json.loads(saved["output_text"])
    errors = validate(result)
    write_json(OUTPUT / "semantic-transcription.json", result)
    report = {
        "record_count": len(result.get("records", [])),
        "structural_validation_passed": not errors,
        "structural_validation_errors": errors,
        "usage": saved["usage"],
        "elapsed_seconds": saved["elapsed_seconds"],
    }
    write_json(OUTPUT / "validation-report.json", report)
    print(json.dumps(report, indent=2, default=str), flush=True)
    if errors:
        raise RuntimeError(f"Sol output failed {len(errors)} structural checks.")


if __name__ == "__main__":
    main()
