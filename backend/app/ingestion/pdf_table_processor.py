# ========================================
# File: pdf_table_processor.py
# ========================================
#
# Purpose
# -------
# Run the complete PDF table-processing pipeline.
#
# Responsibilities
# ----------------
# - Extract table fragments from every PDF page.
# - Merge fragments continuing across pages.
# - Normalize logical tables into generic JSON.
#
# ========================================

from pathlib import Path

import pdfplumber
from app.ingestion.table_gap_checker import TableGapChecker

from app.ingestion.pdfplumber_table_extractor import (
    PdfPlumberTableExtractor,
)
from app.ingestion.table_continuation_merger import (
    TableContinuationMerger,
)
from app.ingestion.table_normalizer import TableNormalizer


# ==========================================================
# PDF Table Processor
# ==========================================================

class PDFTableProcessor:

    # Create the three reusable table-processing stages.
    def __init__(self):
        self.extractor = PdfPlumberTableExtractor()
        self.merger = TableContinuationMerger()
        self.normalizer = TableNormalizer()

    # Return normalized tables from one complete PDF.
    def process(self, pdf_path: Path, borderless_regions: dict[int, list[tuple]] | None = None) -> list[dict]:
        fragments = []
        page_context = {}

        # Open the PDF once for all page-level table work.
        with pdfplumber.open(pdf_path) as pdf_document:

            # Preserve the original one-based page order.
            for page_number, page in enumerate(
                pdf_document.pages,
                start=1,
            ):
                page_tables = (
                    self.extractor.extract_page_tables(
                        page=page,
                        page_number=page_number,
                        **({'borderless_regions': borderless_regions[page_number]}
                           if borderless_regions and page_number in borderless_regions else {}),
                    )
                )
                fragments.extend(page_tables)
                page_context[page_number] = {'height': float(page.height),
                                             'words': page.extract_words(), 'images': page.images}

        # Join fragments that continue across page breaks.
        logical_tables = self.merger.merge_tables(
            fragments,
            gap_checker=TableGapChecker(page_context),
        )

        # Produce dimension-independent JSON structures.
        return [
            self.normalizer.normalize_logical_table(table)
            for table in logical_tables
        ]
