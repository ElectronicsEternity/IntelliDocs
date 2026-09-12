# ========================================
# File: pdfplumber_table_extractor.py
# ========================================
#
# Purpose
# -------
# Test production PDF table processing.
#
# Responsibilities
# ----------------
# - Select known table pages for manual inspection.
# - Call production extraction and normalization.
# - Call the production terminal renderer.
# - Print tables and meaningful JSON.
# - Perform no database writes.
#
# ========================================

# Import json for readable normalized output.
import json

# Import Path for locating the test PDF.
from pathlib import Path

# Import pdfplumber for opening the test PDF.
import pdfplumber

# Import the production extractor under test.
from app.ingestion.pdfplumber_table_extractor import (
    PdfPlumberTableExtractor,
)

# Import the production normalizer under test.
from app.ingestion.table_normalizer import TableNormalizer

# Import the production continuation merger.
from app.ingestion.table_continuation_merger import (
    TableContinuationMerger,
)

# Import the production terminal renderer under test.
from app.ingestion.table_terminal_renderer import (
    TableTerminalRenderer,
)


# ==========================================================
# Test Configuration
# ==========================================================

# Locate the IntelliDocs project root.
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Locate the PDF containing wage tables.
PDF_FILE = (
    PROJECT_ROOT
    / "documents"
    / "56. P.U. (A) 2022_140 "
    "Perintah Gaji Minimum 2022.pdf"
)

# Focus this manual test on known table pages.
TEST_PAGE_NUMBERS = [3, 4, 5, 7, 8, 9]


# ==========================================================
# Test Execution
# ==========================================================

# Run production table processing on configured pages.
def main() -> None:

    # Create the production extractor under test.
    extractor = PdfPlumberTableExtractor()

    # Create the production normalizer under test.
    normalizer = TableNormalizer()

    # Create the production continuation merger.
    merger = TableContinuationMerger()

    # Create the production terminal renderer under test.
    renderer = TableTerminalRenderer()

    # Collect all fragments before continuation analysis.
    extracted_tables = []

    # Display the fixed manual test inputs.
    print(f"PDF: {PDF_FILE.name}")
    print(f"Pages tested: {TEST_PAGE_NUMBERS}")
    print("\n=== Table Processing Started ===")

    # Open the PDF once for all configured pages.
    with pdfplumber.open(PDF_FILE) as document:

        # Process every selected one-based page number.
        for page_number in TEST_PAGE_NUMBERS:

            # Convert the page number to a list index.
            page = document.pages[page_number - 1]

            # Call the production table extractor.
            tables = extractor.extract_page_tables(
                page=page,
                page_number=page_number,
            )

            # Preserve fragments for document-level merging.
            extracted_tables.extend(tables)

    # Merge confirmed cross-page table continuations.
    logical_tables = merger.merge_tables(extracted_tables)

    # Display each complete logical table in document order.
    for index, logical_table in enumerate(
        logical_tables,
        start=1,
    ):

        # Normalize all fragments as one complete table.
        normalized = normalizer.normalize_logical_table(
            logical_table
        )

        # Clearly separate each complete logical table.
        print("\n" + "=" * 63)
        print(
            f"Logical Table {index} | "
            f"pages={logical_table.page_numbers} | "
            f"fragments={len(logical_table.fragments)} | "
            f"merged={logical_table.is_merged}"
        )

        # Display evidence used for confirmed merges.
        for reasons in logical_table.merge_reasons:
            print(f"Merge evidence: {', '.join(reasons)}")

        # Display uncertain continuation warnings.
        for warning in logical_table.warnings:
            print(f"WARNING: {warning}")

        # Render the complete normalized logical table.
        rendered_table = renderer.render(
            cells=normalized["cells"],
            column_count=logical_table.column_count,
        )

        # Display the reconstructed logical table.
        print(rendered_table)

        # Keep terminal JSON focused on generic structure.
        displayed_json = {
            "page_numbers": normalized["page_numbers"],
            "fragment_count": normalized[
                "fragment_count"
            ],
            "is_merged": normalized["is_merged"],
            "status": normalized["status"],
            "source_alignment_valid": normalized[
                "source_alignment_valid"
            ],
            "validation_issues": normalized[
                "validation_issues"
            ],
            "row_count": normalized["row_count"],
            "column_count": normalized[
                "column_count"
            ],
            "rows": normalized["rows"],
        }

        # Display validated structural JSON.
        print("\nNormalized JSON:")
        print(
            json.dumps(
                displayed_json,
                ensure_ascii=False,
                indent=2,
            )
        )

    # Mark the end of table processing output.
    print("\n=== Table Processing Ended ===")

    # Display the final table-fragment count.
    print(
        f"\nTable fragments: {len(extracted_tables)}"
    )

    # Display the merged logical-table total.
    print(f"Logical tables: {len(logical_tables)}")

    # Confirm this playground performs no persistence.
    print("Database unchanged: True")


# ==========================================================
# Entry Point
# ==========================================================

# Run only when executed directly as a module.
if __name__ == "__main__":
    main()
