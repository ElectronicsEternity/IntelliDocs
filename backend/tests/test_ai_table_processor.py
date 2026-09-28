from pathlib import Path
import json

from pypdf import PdfWriter
import pytest

from app.ingestion.ai_table_processor import AIVisualTableProcessor


def test_model_matrix_is_normalized_for_existing_chunker():
    normalized = AIVisualTableProcessor._normalize({
        "table_id": "table-1",
        "title": "Rates",
        "start_page": 4,
        "end_page": 5,
        "column_count": 2,
        "columns": ["Area", "Rate"],
        "row_count": 1,
        "rows": [{
            "row_number": 1,
            "cells": ["City", "RM1,200"],
            "source_pages": [4, 5],
        }],
    }, 1)

    assert normalized["page_numbers"] == [4, 5]
    assert normalized["row_count"] == 2
    assert normalized["column_count"] == 2
    assert [cell["value"] for cell in normalized["cells"]] == [
        "Area", "Rate", "City", "RM1,200",
    ]
    assert all(cell["source_table"] == 1 for cell in normalized["cells"])


def _one_page_pdf(path: Path) -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    with path.open("wb") as output:
        writer.write(output)


def test_validated_table_outputs_are_saved_and_reused(tmp_path, monkeypatch):
    pdf_path = tmp_path / "document.pdf"
    _one_page_pdf(pdf_path)
    profile = {
        "document_title": "Test",
        "page_count": 1,
        "tables": [{
            "table_id": "front-matter",
            "title": "Publication history",
            "start_page": 1,
            "end_page": 1,
            "border_style": "borderless",
            "extraction_mode": "regular_matrix",
            "column_count": 2,
            "header_row_count": 0,
            "data_row_count": 1,
            "column_headings": ["Event", "Date"],
            "page_regions": [{
                "page": 1, "left": 100, "top": 100,
                "right": 900, "bottom": 900,
            }],
        }],
    }
    matrices = {
        "document_title": "Test",
        "tables": [{
            "table_id": "front-matter",
            "title": "Publication history",
            "start_page": 1,
            "end_page": 1,
            "column_count": 2,
            "columns": ["Event", "Date"],
            "row_count": 1,
            "rows": [{
                "row_number": 1,
                "cells": ["Revised", "1981"],
                "source_pages": [1],
            }],
        }],
    }
    processor = AIVisualTableProcessor(
        client=object(),
        profiles_folder=tmp_path / "profiles",
    )
    calls = []

    def structured_call(**kwargs):
        calls.append(kwargs["activity"])
        return profile if kwargs["activity"] == "table_identification" else matrices

    monkeypatch.setattr(processor, "_structured_call", structured_call)
    first = processor.process(pdf_path, owner_id="user", document_id="document")

    cache_folder = tmp_path / "profiles" / "user" / "document"
    assert calls == ["table_identification", "regular_table_extraction"]
    assert first[0]["table_id"] == "front-matter"
    for filename in (
        "table_profile.json",
        "regular_table_matrices.json",
        "semantic_table_matrices.json",
        "normalized_tables.json",
    ):
        assert (cache_folder / filename).is_file()

    cached_processor = AIVisualTableProcessor(
        client=object(),
        profiles_folder=tmp_path / "profiles",
    )
    monkeypatch.setattr(
        cached_processor,
        "_structured_call",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("OpenAI must not be called for a valid cache")
        ),
    )

    assert cached_processor.process(
        pdf_path,
        owner_id="user",
        document_id="document",
    ) == first


def test_rejected_matrix_response_is_saved_for_diagnosis(tmp_path, monkeypatch):
    pdf_path = tmp_path / "document.pdf"
    _one_page_pdf(pdf_path)
    profile = {
        "document_title": "Test",
        "page_count": 1,
        "tables": [{
            "table_id": "table-1",
            "title": "Rates",
            "start_page": 1,
            "end_page": 1,
            "border_style": "bordered",
            "extraction_mode": "regular_matrix",
            "column_count": 2,
            "header_row_count": 1,
            "data_row_count": 1,
            "column_headings": ["Area", "Rate"],
            "page_regions": [{
                "page": 1, "left": 100, "top": 100,
                "right": 900, "bottom": 900,
            }],
        }],
    }
    invalid_matrix = {
        "document_title": "Test",
        "tables": [{
            "table_id": "table-1",
            "title": "Rates",
            "start_page": 1,
            "end_page": 1,
            "column_count": 2,
            "columns": ["Area", "Rate"],
            "row_count": 0,
            "rows": [],
        }],
    }
    processor = AIVisualTableProcessor(
        client=object(),
        profiles_folder=tmp_path / "profiles",
    )
    monkeypatch.setattr(
        processor,
        "_structured_call",
        lambda **kwargs: (
            profile
            if kwargs["activity"] == "table_identification"
            else invalid_matrix
        ),
    )

    with pytest.raises(ValueError, match="Table extraction validation failed"):
        processor.process(pdf_path, owner_id="user", document_id="document")

    saved_path = (
        tmp_path / "profiles" / "user" / "document"
        / "regular_table_matrices.json"
    )
    assert json.loads(saved_path.read_text(encoding="utf-8")) == invalid_matrix
