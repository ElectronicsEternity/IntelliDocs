# ========================================
# File: pymupdf_parser_adapter.py
# ========================================
#
# Purpose
# -------
# Extract PDF pages using PyMuPDF.
#
# Responsibilities
# ----------------
# - Open a PDF using PyMuPDF.
# - Extract plain text from every page.
# - Convert extracted pages into IntelliDocs Page objects.
#
# ========================================

# Import Path for the PDF file location.
from pathlib import Path

# Import PyMuPDF using the existing fitz module name.
import fitz

# Import the shared parser contract.
from app.ingestion.parser_interface import PDFParserInterface

# Import the shared Page model.
from app.models.page import Page


# ==========================================================
# PyMuPDF Adapter
# ==========================================================

# Adapt PyMuPDF output to the common IntelliDocs parser interface.
class PyMuPDFParserAdapter(PDFParserInterface):

    # Extract every PDF page using the existing PyMuPDF behaviour.
    def extract_pages(self, pdf_path: Path) -> list[Page]:

        # Store the Page objects created from the PDF.
        pages = []

        # Open the PDF and close it automatically after extraction.
        with fitz.open(pdf_path) as pdf_document:

            # Process every zero-based page index in the PDF.
            for page_index in range(pdf_document.page_count):

                # Load the current PDF page.
                pdf_page = pdf_document.load_page(page_index)

                # Extract text exactly as the original parser did.
                page_text = str(pdf_page.get_text("text"))

                # Store the extracted text using a one-based page number.
                pages.append(
                    Page(
                        page_number=page_index + 1,
                        text=page_text.strip(),
                    )
                )

        # Return every extracted page to the main PDFParser.
        return pages
