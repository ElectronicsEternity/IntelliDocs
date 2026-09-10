from pathlib import Path
from time import perf_counter

import pdfplumber
import pymupdf
from pypdf import PdfReader


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PDF_FILE = (
    PROJECT_ROOT
    / "documents"
    / "56. P.U. (A) 2022_140 Perintah Gaji Minimum 2022.pdf"
)
OUTPUT_DIRECTORY = PROJECT_ROOT / "outputs" / "pdf_parser_comparison"


def format_output(parser_name, method, pages, elapsed_seconds):
    # Use the same page markers in every file to make comparison easier.
    output_parts = [
        f"Parser: {parser_name}",
        f"Method: {method}",
        f"PDF: {PDF_FILE.name}",
        f"Pages: {len(pages)}",
        f"Extraction time: {elapsed_seconds:.4f} seconds",
    ]

    for page_number, text in enumerate(pages, start=1):
        output_parts.append(f"\n{'=' * 40} PAGE {page_number} {'=' * 40}\n")
        output_parts.append(text.strip())

    return "\n".join(output_parts)


def extract_with_pymupdf():
    # sort=True asks PyMuPDF to follow visual top-to-bottom reading order.
    started_at = perf_counter()

    with pymupdf.open(PDF_FILE) as document:
        pages = [page.get_text("text", sort=True) for page in document]

    return pages, perf_counter() - started_at


def extract_with_pdfplumber():
    # layout=True asks pdfplumber to preserve the visible page arrangement.
    started_at = perf_counter()

    with pdfplumber.open(PDF_FILE) as document:
        pages = [page.extract_text(layout=True) or "" for page in document.pages]

    return pages, perf_counter() - started_at


def extract_with_pypdf():
    # Layout mode uses text coordinates to reconstruct the page reading order.
    started_at = perf_counter()
    document = PdfReader(PDF_FILE)
    pages = [page.extract_text(extraction_mode="layout") or "" for page in document.pages]
    return pages, perf_counter() - started_at


def save_output(filename, parser_name, method, pages, elapsed_seconds):
    output_text = format_output(
        parser_name=parser_name,
        method=method,
        pages=pages,
        elapsed_seconds=elapsed_seconds,
    )
    output_path = OUTPUT_DIRECTORY / filename
    output_path.write_text(output_text, encoding="utf-8")
    print(f"Created: {output_path}")


def main():
    OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)

    print(f"PDF: {PDF_FILE.name}")
    print("\n=== Full PDF Parser Comparison Started ===")

    pymupdf_pages, pymupdf_time = extract_with_pymupdf()
    save_output(
        "pymupdf_output.txt",
        "PyMuPDF",
        'page.get_text("text", sort=True)',
        pymupdf_pages,
        pymupdf_time,
    )

    pdfplumber_pages, pdfplumber_time = extract_with_pdfplumber()
    save_output(
        "pdfplumber_output.txt",
        "pdfplumber",
        "page.extract_text(layout=True)",
        pdfplumber_pages,
        pdfplumber_time,
    )

    pypdf_pages, pypdf_time = extract_with_pypdf()
    save_output(
        "pypdf_output.txt",
        "pypdf",
        'page.extract_text(extraction_mode="layout")',
        pypdf_pages,
        pypdf_time,
    )

    print("=== Full PDF Parser Comparison Ended ===")
    print(f"\nOutput folder: {OUTPUT_DIRECTORY}")


if __name__ == "__main__":
    main()
