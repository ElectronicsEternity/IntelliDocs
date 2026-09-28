"""One visual table-only API call per PDF, followed by local guided extraction."""

import argparse
import base64
import hashlib
import json
from decimal import Decimal
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from openai import OpenAI

from app.config import settings
from app.indexing.table_profile import (
    TABLE_PROFILE_PROMPT,
    TABLE_PROFILE_SCHEMA,
    validate_table_profile,
)
from app.ingestion.profile_guided_table_processor import ProfileGuidedTableProcessor
from app.services.usage.ai_usage import build_record

BASE = Path(__file__).resolve().parents[2] / "backups" / "2026-09-17"
MODEL = "gpt-5.6-sol"
DOCUMENTS = {
    "akta": "Akta Kerja 1955 (Akta 265).pdf",
    "perintah": "56. P.U. (A) 2022_140 Perintah Gaji Minimum 2022.pdf",
}


def pdf_page_count(path):
    import pypdf
    return len(pypdf.PdfReader(path).pages)


def _apply_cost_rates(usage):
    """Attach the reviewed GPT-5.6 Sol standard rates to one saved usage row."""
    if usage["input_tokens"] is None or usage["output_tokens"] is None:
        return usage
    input_rate = Decimal("4")
    cached_rate = Decimal("0.4")
    output_rate = Decimal("20")
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


def run(name, retry_failed=False):
    pdf = BASE / "pdfs" / DOCUMENTS[name]
    folder = BASE / f"{name}-table-profile-gpt56-high"
    folder.mkdir(exist_ok=True)
    metadata = {
        "document": pdf.name,
        "pdf_sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
        "page_count": pdf_page_count(pdf),
        "model": MODEL,
        "reasoning_effort": "high",
        "prompt_sha256": hashlib.sha256(TABLE_PROFILE_PROMPT.encode()).hexdigest(),
        "schema_sha256": hashlib.sha256(
            json.dumps(TABLE_PROFILE_SCHEMA, sort_keys=True).encode()
        ).hexdigest(),
    }
    response_file = folder / "response.json"
    if response_file.exists() and retry_failed:
        previous = json.loads(response_file.read_text(encoding="utf-8"))
        if previous.get("response") is not None:
            raise RuntimeError(f"{name} already has a model response; refusing another paid call.")
        if previous.get("error_type") != "RateLimitError":
            raise RuntimeError(f"{name} failure was not the reviewed quota error; refusing retry.")
        (folder / "attempt-1-quota-error.json").write_text(
            response_file.read_text(encoding="utf-8"), encoding="utf-8"
        )
        marker = folder / "request-started.json"
        if marker.exists():
            (folder / "attempt-1-request-started.json").write_text(
                marker.read_text(encoding="utf-8"), encoding="utf-8"
            )
        response_file.unlink()
        marker.unlink(missing_ok=True)
    if response_file.exists():
        saved = json.loads(response_file.read_text(encoding="utf-8"))
        if saved["metadata"] != metadata:
            raise RuntimeError("Cached table response uses different inputs.")
        print(f"Reusing saved {name} response; no paid call.", flush=True)
    else:
        marker = folder / "request-started.json"
        if marker.exists():
            raise RuntimeError(f"A prior {name} request may have incurred cost; refusing retry.")
        if not settings.OPENAI_API_KEY:
            raise RuntimeError("OpenAI API key is unavailable.")
        marker.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        (folder / "prompt.txt").write_text(TABLE_PROFILE_PROMPT, encoding="utf-8")
        encoded = base64.b64encode(pdf.read_bytes()).decode("ascii")
        client = OpenAI(api_key=settings.OPENAI_API_KEY, max_retries=0, timeout=1200)
        response, error = None, None
        started = time.monotonic()
        try:
            response = client.responses.create(
                model=MODEL,
                reasoning={"effort": "high"},
                max_output_tokens=20000,
                input=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "input_file",
                            "filename": pdf.name,
                            "file_data": f"data:application/pdf;base64,{encoded}",
                            "detail": "high",
                        },
                        {"type": "input_text", "text": TABLE_PROFILE_PROMPT},
                    ],
                }],
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "pdf_table_profile",
                        "strict": True,
                        "schema": TABLE_PROFILE_SCHEMA,
                    }
                },
            )
        except Exception as exc:
            error = exc
        usage = _apply_cost_rates(build_record(
            response, activity="table_profiling_experiment", model=MODEL,
            user_id="offline-review", error=error,
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
        response_file.write_text(json.dumps(saved, indent=2, default=str), encoding="utf-8")
        if error:
            raise RuntimeError(f"{name} API request failed: {type(error).__name__}.")
    if not saved["response"] or saved["response"]["status"] != "completed":
        raise RuntimeError(f"{name} response was not completed.")
    profile = json.loads(saved["output_text"])
    errors = validate_table_profile(profile, metadata["page_count"])
    (folder / "table-profile.json").write_text(
        json.dumps(profile, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    if errors:
        (folder / "validation-errors.json").write_text(
            json.dumps(list(errors), indent=2), encoding="utf-8"
        )
        raise RuntimeError(f"{name} table profile failed {len(errors)} cross-field checks.")
    tables, diagnostics = ProfileGuidedTableProcessor().process(pdf, profile)
    (folder / "normalized-tables.json").write_text(
        json.dumps(tables, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    report = {
        "profile_table_count": len(profile["tables"]),
        "extracted_table_count": len(tables),
        "diagnostics": diagnostics,
        "usage": saved["usage"],
        "elapsed_seconds": saved["elapsed_seconds"],
    }
    (folder / "comparison.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8"
    )
    print(json.dumps({name: report}, indent=2, default=str), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("documents", nargs="+", choices=DOCUMENTS)
    parser.add_argument(
        "--retry-failed", action="store_true",
        help="Retry only a preserved zero-response quota failure.",
    )
    arguments = parser.parse_args()
    for document_name in arguments.documents:
        run(document_name, retry_failed=arguments.retry_failed)
