"""Extract complete table matrices from Sol-located PDF page subsets using Terra."""

import argparse
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
from app.indexing.table_matrix import (
    TABLE_MATRIX_SCHEMA,
    build_table_matrix_prompt,
    validate_table_matrices,
)
from app.services.usage.ai_usage import build_record


BASE = Path(__file__).resolve().parents[2] / "backups" / "2026-09-17"
MODEL = "gpt-5.6-terra"
DOCUMENTS = {
    "akta": "Akta Kerja 1955 (Akta 265).pdf",
    "perintah": "56. P.U. (A) 2022_140 Perintah Gaji Minimum 2022.pdf",
}


def _json_write(path: Path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def _selected_pages(profile):
    return sorted({
        page
        for table in profile["tables"]
        for page in range(table["start_page"], table["end_page"] + 1)
    })


def _create_subset(source: Path, target: Path, selected_pages: list[int]):
    reader = PdfReader(source)
    writer = PdfWriter()
    for original_page in selected_pages:
        writer.add_page(reader.pages[original_page - 1])
    with target.open("wb") as handle:
        writer.write(handle)
    return [
        {"subset_page": index, "original_page": original_page}
        for index, original_page in enumerate(selected_pages, 1)
    ]


def _apply_terra_cost_rates(usage):
    """Apply official GPT-5.6 Terra standard rates to actual reported usage."""
    if usage["input_tokens"] is None or usage["output_tokens"] is None:
        return usage
    # Long-context rates apply to a request whose input exceeds 272K tokens.
    long_context = usage["input_tokens"] > 272_000
    input_rate = Decimal("4") if long_context else Decimal("2")
    cached_rate = Decimal("0.4") if long_context else Decimal("0.2")
    output_rate = Decimal("18") if long_context else Decimal("12")
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


def run(name: str):
    source = BASE / "pdfs" / DOCUMENTS[name]
    profile_path = BASE / f"{name}-table-profile-gpt56-high" / "table-profile.json"
    output = BASE / f"{name}-table-matrix-gpt56-terra-high"
    output.mkdir(exist_ok=True)
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    selected_pages = _selected_pages(profile)
    subset_path = output / "selected-pages.pdf"
    page_map = _create_subset(source, subset_path, selected_pages)
    prompt = build_table_matrix_prompt(profile, page_map)
    metadata = {
        "document": source.name,
        "source_pdf_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "source_table_profile_sha256": hashlib.sha256(profile_path.read_bytes()).hexdigest(),
        "selected_pdf_sha256": hashlib.sha256(subset_path.read_bytes()).hexdigest(),
        "selected_original_pages": selected_pages,
        "selected_page_count": len(selected_pages),
        "model": MODEL,
        "reasoning_effort": "high",
        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        "schema_sha256": hashlib.sha256(
            json.dumps(TABLE_MATRIX_SCHEMA, sort_keys=True).encode()
        ).hexdigest(),
    }
    _json_write(output / "page-map.json", page_map)
    (output / "prompt.txt").write_text(prompt, encoding="utf-8")
    response_file = output / "response.json"
    if response_file.exists():
        saved = json.loads(response_file.read_text(encoding="utf-8"))
        if saved["metadata"] != metadata:
            raise RuntimeError(f"Cached {name} response uses different inputs.")
        print(f"Reusing saved {name} Terra response; no paid call.", flush=True)
    else:
        marker = output / "request-started.json"
        if marker.exists():
            raise RuntimeError(f"A prior {name} request may have incurred cost; refusing retry.")
        if not settings.OPENAI_API_KEY:
            raise RuntimeError("OpenAI API key is unavailable.")
        _json_write(marker, metadata)
        encoded = base64.b64encode(subset_path.read_bytes()).decode("ascii")
        client = OpenAI(api_key=settings.OPENAI_API_KEY, max_retries=0, timeout=1200)
        response, error = None, None
        started = time.monotonic()
        try:
            response = client.responses.create(
                model=MODEL,
                reasoning={"effort": "high"},
                max_output_tokens=65536 if name == "akta" else 24000,
                input=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "input_file",
                            "filename": subset_path.name,
                            "file_data": f"data:application/pdf;base64,{encoded}",
                            "detail": "high",
                        },
                        {"type": "input_text", "text": prompt},
                    ],
                }],
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "pdf_table_matrices",
                        "strict": True,
                        "schema": TABLE_MATRIX_SCHEMA,
                    }
                },
            )
        except Exception as exc:
            error = exc
        usage = _apply_terra_cost_rates(build_record(
            response, activity="table_matrix_extraction_experiment", model=MODEL,
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
        _json_write(response_file, saved)
        if error:
            raise RuntimeError(f"{name} API request failed: {type(error).__name__}: {error}")
    if not saved["response"] or saved["response"]["status"] != "completed":
        raise RuntimeError(f"{name} Terra response was not completed.")
    matrices = json.loads(saved["output_text"])
    errors = validate_table_matrices(matrices, profile)
    _json_write(output / "table-matrices.json", matrices)
    report = {
        "document": name,
        "selected_original_pages": selected_pages,
        "selected_page_count": len(selected_pages),
        "table_count": len(matrices.get("tables", [])),
        "validation_passed": not errors,
        "validation_errors": list(errors),
        "usage": saved["usage"],
        "elapsed_seconds": saved["elapsed_seconds"],
    }
    _json_write(output / "validation-report.json", report)
    print(json.dumps(report, indent=2, default=str), flush=True)
    if errors:
        raise RuntimeError(f"{name} Terra matrix output failed {len(errors)} checks.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("documents", nargs="+", choices=DOCUMENTS)
    arguments = parser.parse_args()
    for document_name in arguments.documents:
        run(document_name)
