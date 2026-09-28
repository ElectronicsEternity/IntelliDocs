"""Production visual table identification and lossless transcription."""

import base64
import hashlib
from io import BytesIO
import json
from pathlib import Path
import re

from openai import OpenAI
from pypdf import PdfReader, PdfWriter

from app.config import settings
from app.indexing.table_matrix import (
    TABLE_MATRIX_SCHEMA,
    build_table_matrix_prompt,
    validate_table_matrices,
)
from app.indexing.table_profile import (
    TABLE_PROFILE_PROMPT,
    TABLE_PROFILE_SCHEMA,
    validate_table_profile,
)
from app.services.usage.ai_usage import tracked_ai_call


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROFILES_FOLDER = PROJECT_ROOT / "documents" / "Profiles"
TABLE_CACHE_VERSION = 1


class AIVisualTableProcessor:
    """Use visual models for table discovery and table-type-specific extraction."""

    def __init__(
        self,
        client: OpenAI | None = None,
        profiles_folder: Path | None = None,
    ):
        self.client = client or OpenAI(
            api_key=settings.OPENAI_API_KEY,
            max_retries=0,
            timeout=1200,
        )
        self.profiles_folder = profiles_folder or DEFAULT_PROFILES_FOLDER

    @staticmethod
    def _safe_folder_name(value: str) -> str:
        return re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._") or "unknown"

    def _cache_folder(self, owner_id: str, document_id: str) -> Path:
        folder = (
            self.profiles_folder
            / self._safe_folder_name(owner_id)
            / self._safe_folder_name(document_id)
        )
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    @staticmethod
    def _json_hash(value) -> str:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _cache_manifest(self, source_data: bytes, page_count: int) -> dict:
        return {
            "cache_version": TABLE_CACHE_VERSION,
            "source_sha256": hashlib.sha256(source_data).hexdigest(),
            "page_count": page_count,
            "table_profile_model": settings.TABLE_PROFILE_MODEL,
            "regular_table_model": settings.REGULAR_TABLE_MODEL,
            "semantic_table_model": settings.SEMANTIC_TABLE_MODEL,
            "reasoning_effort": settings.TABLE_REASONING_EFFORT,
            "max_output_tokens": settings.TABLE_MAX_OUTPUT_TOKENS,
            "table_profile_prompt_sha256": self._json_hash(TABLE_PROFILE_PROMPT),
            "table_profile_schema_sha256": self._json_hash(TABLE_PROFILE_SCHEMA),
            "table_matrix_schema_sha256": self._json_hash(TABLE_MATRIX_SCHEMA),
        }

    @staticmethod
    def _read_json(path: Path):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    @staticmethod
    def _write_json(path: Path, value) -> None:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(value, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        temporary.replace(path)

    @staticmethod
    def _file_content(filename: str, data: bytes) -> dict:
        encoded = base64.b64encode(data).decode("ascii")
        return {
            "type": "input_file",
            "filename": filename,
            "file_data": f"data:application/pdf;base64,{encoded}",
            "detail": "high",
        }

    def _structured_call(
        self,
        *,
        model: str,
        activity: str,
        filename: str,
        pdf_data: bytes,
        prompt: str,
        schema_name: str,
        schema: dict,
        owner_id: str,
        document_id: str,
    ) -> dict:
        response = tracked_ai_call(
            lambda: self.client.responses.create(
                model=model,
                reasoning={"effort": settings.TABLE_REASONING_EFFORT},
                max_output_tokens=settings.TABLE_MAX_OUTPUT_TOKENS,
                input=[{
                    "role": "user",
                    "content": [
                        self._file_content(filename, pdf_data),
                        {"type": "input_text", "text": prompt},
                    ],
                }],
                text={"format": {
                    "type": "json_schema",
                    "name": schema_name,
                    "strict": True,
                    "schema": schema,
                }},
            ),
            activity=activity,
            model=model,
            user_id=owner_id,
            document_id=document_id,
        )
        if getattr(response, "status", None) != "completed":
            raise ValueError(f"{activity} returned an incomplete response.")
        return json.loads(response.output_text)

    @staticmethod
    def _subset(source_data: bytes, pages: list[int]) -> tuple[bytes, list[dict]]:
        reader = PdfReader(BytesIO(source_data))
        writer = PdfWriter()
        for page in pages:
            writer.add_page(reader.pages[page - 1])
        output = BytesIO()
        writer.write(output)
        page_map = [
            {"subset_page": index, "original_page": page}
            for index, page in enumerate(pages, 1)
        ]
        return output.getvalue(), page_map

    @staticmethod
    def _normalize(matrix: dict, table_number: int) -> dict:
        cells = []
        for column, value in enumerate(matrix["columns"], 1):
            cells.append({
                "value": value,
                "row_start": 1,
                "row_end": 1,
                "column_start": column,
                "column_end": column,
                "source_page": matrix["start_page"],
                "source_table": table_number,
            })
        for row_number, row in enumerate(matrix["rows"], 2):
            source_page = (row.get("source_pages") or [matrix["start_page"]])[0]
            for column, value in enumerate(row["cells"], 1):
                cells.append({
                    "value": value,
                    "row_start": row_number,
                    "row_end": row_number,
                    "column_start": column,
                    "column_end": column,
                    "source_page": source_page,
                    "source_table": table_number,
                })
        page_numbers = sorted({
            page
            for row in matrix["rows"]
            for page in row.get("source_pages", [])
        } or set(range(matrix["start_page"], matrix["end_page"] + 1)))
        return {
            "table_id": matrix["table_id"],
            "title": matrix["title"],
            "page_numbers": page_numbers,
            "fragment_count": len(page_numbers),
            "is_merged": len(page_numbers) > 1,
            "status": "normalized",
            "source_alignment_valid": True,
            "validation_issues": [],
            "row_count": len(matrix["rows"]) + 1,
            "column_count": matrix["column_count"],
            "rows": [],
            "cells": cells,
        }

    def _extract_group(
        self,
        *,
        source_data: bytes,
        source_name: str,
        profile: dict,
        semantic: bool,
        owner_id: str,
        document_id: str,
    ) -> dict:
        pages = sorted({
            page
            for table in profile["tables"]
            for page in range(table["start_page"], table["end_page"] + 1)
        })
        subset, page_map = self._subset(source_data, pages)
        model = settings.SEMANTIC_TABLE_MODEL if semantic else settings.REGULAR_TABLE_MODEL
        activity = "semantic_table_extraction" if semantic else "regular_table_extraction"
        result = self._structured_call(
            model=model,
            activity=activity,
            filename=f"selected-{source_name}",
            pdf_data=subset,
            prompt=build_table_matrix_prompt(profile, page_map, semantic=semantic),
            schema_name="semantic_table_matrices" if semantic else "regular_table_matrices",
            schema=TABLE_MATRIX_SCHEMA,
            owner_id=owner_id,
            document_id=document_id,
        )
        return result

    def process(self, pdf_path: Path, *, owner_id: str, document_id: str) -> list[dict]:
        source_data = pdf_path.read_bytes()
        page_count = len(PdfReader(BytesIO(source_data)).pages)
        cache_folder = self._cache_folder(owner_id, document_id)
        paths = {
            "manifest": cache_folder / "table_cache_manifest.json",
            "profile": cache_folder / "table_profile.json",
            "regular_matrix": cache_folder / "regular_table_matrices.json",
            "semantic_matrix": cache_folder / "semantic_table_matrices.json",
            "normalized": cache_folder / "normalized_tables.json",
        }
        expected_manifest = self._cache_manifest(source_data, page_count)
        cache_matches = self._read_json(paths["manifest"]) == expected_manifest

        profile = self._read_json(paths["profile"]) if cache_matches else None
        profile_errors = (
            validate_table_profile(profile, page_count)
            if isinstance(profile, dict)
            else ("Missing cached table profile.",)
        )
        profile_reused = not profile_errors
        if profile_errors:
            profile = self._structured_call(
                model=settings.TABLE_PROFILE_MODEL,
                activity="table_identification",
                filename=pdf_path.name,
                pdf_data=source_data,
                prompt=TABLE_PROFILE_PROMPT,
                schema_name="pdf_table_profile",
                schema=TABLE_PROFILE_SCHEMA,
                owner_id=owner_id,
                document_id=document_id,
            )
            self._write_json(paths["profile"], profile)
            self._write_json(paths["manifest"], expected_manifest)
            errors = validate_table_profile(profile, page_count)
            if errors:
                raise ValueError("Table profile validation failed: " + " ".join(errors))
        else:
            print("Stage tables: reused validated table_profile.json.")

        extracted_by_id = {}
        for mode, semantic in (("regular_matrix", False), ("semantic_records", True)):
            tables = [table for table in profile["tables"] if table["extraction_mode"] == mode]
            group = {**profile, "tables": tables}
            cache_key = "semantic_matrix" if semantic else "regular_matrix"
            result = (
                self._read_json(paths[cache_key])
                if cache_matches and profile_reused
                else None
            )
            matrix_errors = (
                validate_table_matrices(result, group)
                if isinstance(result, dict)
                else ("Missing cached table matrices.",)
            )
            if matrix_errors:
                if tables:
                    result = self._extract_group(
                        source_data=source_data,
                        source_name=pdf_path.name,
                        profile=group,
                        semantic=semantic,
                        owner_id=owner_id,
                        document_id=document_id,
                    )
                else:
                    result = {
                        "document_title": profile["document_title"],
                        "tables": [],
                    }
                self._write_json(paths[cache_key], result)
                errors = validate_table_matrices(result, group)
                if errors:
                    raise ValueError(
                        "Table extraction validation failed: "
                        + " ".join(errors)
                    )
            else:
                print(f"Stage tables: reused validated {paths[cache_key].name}.")
            for matrix in result["tables"]:
                extracted_by_id[matrix["table_id"]] = matrix
        normalized = [
            self._normalize(extracted_by_id[table["table_id"]], index)
            for index, table in enumerate(profile["tables"], 1)
        ]
        cached_normalized = (
            self._read_json(paths["normalized"])
            if cache_matches and profile_reused
            else None
        )
        if cached_normalized == normalized:
            print("Stage tables: reused validated normalized_tables.json.")
        else:
            self._write_json(paths["normalized"], normalized)
        return normalized
