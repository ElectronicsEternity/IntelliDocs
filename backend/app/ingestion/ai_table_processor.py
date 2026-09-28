"""Production visual table identification and lossless transcription."""

import base64
from io import BytesIO
import json
from pathlib import Path

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


class AIVisualTableProcessor:
    """Use visual models for table discovery and table-type-specific extraction."""

    def __init__(self, client: OpenAI | None = None):
        self.client = client or OpenAI(
            api_key=settings.OPENAI_API_KEY,
            max_retries=0,
            timeout=1200,
        )

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
    ) -> list[dict]:
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
        errors = validate_table_matrices(result, profile)
        if errors:
            raise ValueError("Table extraction validation failed: " + " ".join(errors))
        return result["tables"]

    def process(self, pdf_path: Path, *, owner_id: str, document_id: str) -> list[dict]:
        source_data = pdf_path.read_bytes()
        page_count = len(PdfReader(BytesIO(source_data)).pages)
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
        errors = validate_table_profile(profile, page_count)
        if errors:
            raise ValueError("Table profile validation failed: " + " ".join(errors))
        extracted_by_id = {}
        for mode, semantic in (("regular_matrix", False), ("semantic_records", True)):
            tables = [table for table in profile["tables"] if table["extraction_mode"] == mode]
            if not tables:
                continue
            group = {**profile, "tables": tables}
            for matrix in self._extract_group(
                source_data=source_data,
                source_name=pdf_path.name,
                profile=group,
                semantic=semantic,
                owner_id=owner_id,
                document_id=document_id,
            ):
                extracted_by_id[matrix["table_id"]] = matrix
        return [
            self._normalize(extracted_by_id[table["table_id"]], index)
            for index, table in enumerate(profile["tables"], 1)
        ]
