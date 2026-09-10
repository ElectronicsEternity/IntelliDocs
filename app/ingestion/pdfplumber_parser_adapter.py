# ========================================
# File: pdfplumber_parser_adapter.py
# ========================================
#
# Purpose
# -------
# Extract PDF pages using pdfplumber.
#
# Responsibilities
# ----------------
# - Open a PDF using pdfplumber.
# - Extract layout-aware text from every page.
# - Convert extracted pages into IntelliDocs Page objects.
#
# ========================================

# Import Path for the PDF file location.
from pathlib import Path

# Import the pdfplumber extraction library.
import pdfplumber

# Import the shared parser contract.
from app.ingestion.parser_interface import PDFParserInterface

# Import the shared Page model.
from app.models.page import Page


# ==========================================================
# pdfplumber Adapter
# ==========================================================

# Adapt pdfplumber output to the common IntelliDocs parser interface.
class PdfPlumberParserAdapter(PDFParserInterface):

    # Extract every PDF page using layout-aware text extraction.
    def extract_pages(self, pdf_path: Path) -> list[Page]:

        # Store the Page objects created from the PDF.
        pages = []

        # Open the PDF and close it automatically after extraction.
        with pdfplumber.open(pdf_path) as pdf_document:

            # Process every page with a one-based page number.
            for page_number, pdf_page in enumerate(pdf_document.pages, start=1):

                # Preserve the visible arrangement of page text and tables.
                page_text = pdf_page.extract_text(layout=True) or ""

                # Store the extracted text using the shared Page model.
                pages.append(
                    Page(
                        page_number=page_number,
                        text=page_text.strip(),
                    )
                )

        # Return every extracted page to the main PDFParser.
        return pages
