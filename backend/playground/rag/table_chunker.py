import os
# ========================================
# File: table_chunker.py
# ========================================
#
# Purpose
# -------
# Test table chunking with a real PDF.
#
# Responsibilities
# ----------------
# - Extract tables from every PDF page.
# - Merge confirmed table continuations.
# - Normalize tables using geometry.
# - Create one searchable chunk per logical table.
# - Inspect chunk text and metadata without database access.
#
# ========================================

# Import Path for locating the real test PDF.
from pathlib import Path

# Import pdfplumber for page-level table detection.
import pdfplumber

# Import the production PDF parser.
from app.ingestion.parser import PDFParser

# Import the production table extractor.
from app.ingestion.pdfplumber_table_extractor import (
    PdfPlumberTableExtractor,
)

# Import the production continuation merger.
from app.ingestion.table_continuation_merger import (
    TableContinuationMerger,
)

# Import the production geometry normalizer.
from app.ingestion.table_normalizer import TableNormalizer

# Import the table metadata type for inspection.
from app.models.chunk_metadata import TableChunkMetadata

# Import the production chunker under test.
from app.rag.chunker import Chunker


# ==========================================================
# Test Configuration
# ==========================================================

# Locate the IntelliDocs project root.
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Locate the real PDF containing several table dimensions.
PDF_FILE = (
    PROJECT_ROOT
    / "documents"
    / "56. P.U. (A) 2022_140 "
    "Perintah Gaji Minimum 2022.pdf"
)

# Store verified table page groups for this test PDF.
EXPECTED_TABLE_PAGES = [
    (3,),
    (4,),
    (4, 5),
    (5,),
    (7,),
    (8,),
    (8, 9),
    (9,),
]


# ==========================================================
# Test Execution
# ==========================================================

# Run the complete table-to-chunk workflow without writes.
def main() -> None:

    # Parse document metadata and page text.
    document = PDFParser(PDF_FILE).extract_text(
        owner_id=os.environ["INTELLIDOCS_DEV_USER_ID"]
    )

    # Create each production component under test.
    extractor = PdfPlumberTableExtractor()
    merger = TableContinuationMerger()
    normalizer = TableNormalizer()
    chunker = Chunker()

    # Collect physical table fragments from every page.
    fragments = []

    # Open the PDF once for complete table extraction.
    with pdfplumber.open(PDF_FILE) as pdf_document:

        # Inspect every page instead of hardcoding table pages.
        for page_number, page in enumerate(
            pdf_document.pages,
            start=1,
        ):

            # Add every table fragment detected on this page.
            fragments.extend(
                extractor.extract_page_tables(
                    page=page,
                    page_number=page_number,
                )
            )

    # Merge fragments belonging to cross-page tables.
    logical_tables = merger.merge_tables(fragments)

    # Normalize every logical table using only geometry.
    normalized_tables = [
        normalizer.normalize_logical_table(table)
        for table in logical_tables
    ]

    # Convert every normalized table into one chunk.
    chunks = chunker.chunk_tables(
        document=document,
        normalized_tables=normalized_tables,
    )

    # Collect any mismatch found during inspection.
    issues = []

    # Display the real test inputs.
    print(f"PDF: {PDF_FILE.name}")
    print(f"Pages scanned: {document.total_pages}")
    print("\n=== Table Chunking Started ===")

    # Inspect each table and its corresponding chunk.
    for index, chunk in enumerate(chunks, start=1):

        # Load the corresponding normalized table.
        normalized = normalized_tables[index - 1]

        # Load the chunk metadata for type checking.
        metadata = chunk.metadata

        # Record an unexpected metadata model.
        if not isinstance(metadata, TableChunkMetadata):
            issues.append(
                f"Chunk {index} has non-table metadata."
            )
            continue

        # Confirm the source pages remain unchanged.
        expected_pages = tuple(
            normalized["page_numbers"]
        )
        if metadata.page_numbers != expected_pages:
            issues.append(
                f"Chunk {index} has incorrect pages."
            )

        # Confirm table dimensions remain unchanged.
        expected_dimensions = (
            normalized["row_count"],
            normalized["column_count"],
        )
        actual_dimensions = (
            metadata.row_count,
            metadata.column_count,
        )
        if actual_dimensions != expected_dimensions:
            issues.append(
                f"Chunk {index} has incorrect dimensions."
            )

        # Confirm every normalized cell reaches metadata.
        if len(metadata.fields) != len(
            normalized["cells"]
        ):
            issues.append(
                f"Chunk {index} has missing table cells."
            )

        # Confirm the stored token count is reproducible.
        expected_tokens = chunker.tokenizer.count_tokens(
            chunk.text
        )
        if chunk.token_count != expected_tokens:
            issues.append(
                f"Chunk {index} has an incorrect token count."
            )

        # Separate each chunk for readable inspection.
        print("\n" + "=" * 63)
        print(
            f"Chunk {index} | "
            f"table={metadata.table_number} | "
            f"pages={list(metadata.page_numbers)} | "
            f"rows={metadata.row_count} | "
            f"columns={metadata.column_count} | "
            f"cells={len(metadata.fields)} | "
            f"tokens={chunk.token_count}"
        )

        # Display concise source metadata.
        print(f"Document ID: {chunk.document_id}")
        print(f"Document name: {document.filename}")
        print(f"Content type: {chunk.content_type}")

        # Display the exact text prepared for embedding.
        print("Searchable text:")
        print(chunk.text)

    # Load page groups returned by table processing.
    actual_table_pages = [
        tuple(table.page_numbers)
        for table in logical_tables
    ]

    # Check the verified table locations and total.
    correct_table_count = (
        actual_table_pages == EXPECTED_TABLE_PAGES
    )
    one_chunk_per_table = (
        len(chunks) == len(logical_tables)
    )

    # Record unexpected or missing logical tables.
    if not correct_table_count:
        issues.append(
            "Expected table pages "
            f"{EXPECTED_TABLE_PAGES}, received "
            f"{actual_table_pages}."
        )

    # Record any table that failed to become a chunk.
    if not one_chunk_per_table:
        issues.append(
            "Logical-table and chunk counts differ."
        )

    # Mark the end of detailed chunk output.
    print("\n=== Table Chunking Ended ===")

    # Display concise pass-or-fail results.
    print("\nResults:")
    print(f"Table fragments: {len(fragments)}")
    print(f"Logical tables: {len(logical_tables)}")
    print(f"Table chunks: {len(chunks)}")
    print(f"Expected table count: {correct_table_count}")
    print(f"One chunk per table: {one_chunk_per_table}")
    print(f"Chunk issues: {len(issues)}")

    # Display every detected mismatch for investigation.
    for issue in issues:
        print(f"- {issue}")

    # Confirm this playground never opens the database.
    print("Database accessed: False")


# ==========================================================
# Entry Point
# ==========================================================

# Run only when executed directly as a module.
if __name__ == "__main__":
    main()
