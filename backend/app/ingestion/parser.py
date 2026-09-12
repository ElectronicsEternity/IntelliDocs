# ========================================
# File: parser.py
# ========================================
#
# Purpose
# -------
# Coordinate PDF extraction without depending on one PDF library.
#
# Responsibilities
# ----------------
# - Select the configured PDF parser adapter.
# - Extract pages through the common parser interface.
# - Detect the document language.
# - Calculate the file hash.
# - Build the IntelliDocs Document model.
#
# ========================================

# Import hashlib for generating the document fingerprint.
import hashlib

# Import uuid for generating a new document identifier.
import uuid

# Import datetime for recording the document upload time.
from datetime import datetime

# Import Path for handling file and folder paths.
from pathlib import Path

# Import language detection for the complete extracted document.
from langdetect import detect

# Import application constants used while building the Document model.
from app.constants import (
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_JURISDICTION,
    DEFAULT_LANGUAGE,
    DEFAULT_PUBLISHER,
    FILE_READ_CHUNK_SIZE,
    PDF_PARSER_PROVIDER,
)

# Import the common parser contract used by every adapter.
from app.ingestion.parser_interface import PDFParserInterface

# Import the shared Document model returned to the application.
from app.models.document import Document


# ==========================================================
# PDF Parser
# ==========================================================

# Coordinate common document processing around a selected parser adapter.
class PDFParser:

    # Store the PDF path and select the configured adapter.
    def __init__(
        self,
        pdf_path: Path,
        adapter: PDFParserInterface | None = None,
    ):

        # Remember which PDF file should be processed.
        self.pdf_path = pdf_path

        # Use an explicitly supplied adapter or create the configured default.
        self.adapter = adapter or self._create_default_adapter()

    # ==========================================================
    # Adapter Selection
    # ==========================================================

    # Create the adapter selected in the application constants.
    @staticmethod
    def _create_default_adapter() -> PDFParserInterface:

        # Load PyMuPDF only when it is the configured provider.
        if PDF_PARSER_PROVIDER == "pymupdf":

            # Import locally so unused parser libraries are not loaded.
            from app.ingestion.pymupdf_parser_adapter import PyMuPDFParserAdapter

            # Return the PyMuPDF implementation of the common interface.
            return PyMuPDFParserAdapter()

        # Load pdfplumber only when it is the configured provider.
        if PDF_PARSER_PROVIDER == "pdfplumber":

            # Import locally so unused parser libraries are not loaded.
            from app.ingestion.pdfplumber_parser_adapter import PdfPlumberParserAdapter

            # Return the pdfplumber implementation of the common interface.
            return PdfPlumberParserAdapter()

        # Reject configuration values that do not identify a known adapter.
        raise ValueError(f"Unsupported PDF parser provider: {PDF_PARSER_PROVIDER}")

    # ==========================================================
    # PDF File Discovery
    # ==========================================================

    # Return every PDF file found inside the supplied directory.
    @staticmethod
    def get_pdf_files(directory: Path) -> list[Path]:

        # Sort the paths so ingestion order remains predictable.
        return sorted(directory.glob("*.pdf"))

    # ==========================================================
    # Document Extraction
    # ==========================================================

    # Extract the PDF and return a complete IntelliDocs Document.
    def extract_text(
        self,
        owner_id: str,
        document_id: str | None = None,
        original_filename: str | None = None,
    ) -> Document:

        # Delegate only page extraction to the selected library adapter.
        pages = self.adapter.extract_pages(self.pdf_path)

        # Combine non-empty pages for document-level language detection.
        document_text = " ".join(page.text for page in pages if page.text)

        # Fall back to the default language when detection cannot complete.
        try:

            # Detect language using a limited sample of the document text.
            language = detect(document_text[:10000])

        # Handle language detection failures without stopping ingestion.
        except Exception:

            # Use the configured fallback language.
            language = DEFAULT_LANGUAGE

        # Convert the Indonesian code sometimes returned for Malay text.
        if language == "id":

            # Store the correct Malay language code.
            language = "ms"

        # Build the common Document model used by all downstream components.
        document = Document(
            id=document_id or str(uuid.uuid4()),
            filename=original_filename or self.pdf_path.name,
            file_extension=self.pdf_path.suffix.replace(".", ""),
            file_size=self.pdf_path.stat().st_size,
            file_hash=self.calculate_file_hash(self.pdf_path),
            uploaded_at=datetime.now(),
            title=Path(original_filename).stem if original_filename else self.pdf_path.stem,
            total_pages=len(pages),
            language=language,
            jurisdiction=DEFAULT_JURISDICTION,
            document_type=None,
            publisher=DEFAULT_PUBLISHER,
            processing_time_ms=0,
            embedding_model=DEFAULT_EMBEDDING_MODEL,
            indexed_at=None,
            owner_id=owner_id,
            pages=pages,
        )

        # Return the completed Document to the ingestion workflow.
        return document

    # ==========================================================
    # File Hashing
    # ==========================================================

    # Generate the SHA256 fingerprint used for duplicate detection.
    def calculate_file_hash(self, file_path: Path) -> str:

        # Create an empty SHA256 hash calculation.
        sha256 = hashlib.sha256()

        # Open the PDF in binary mode and close it automatically afterward.
        with open(file_path, "rb") as file:

            # Read the PDF incrementally instead of loading it all into memory.
            while chunk := file.read(FILE_READ_CHUNK_SIZE):

                # Add the current group of bytes to the hash calculation.
                sha256.update(chunk)

        # Return the completed fingerprint as hexadecimal text.
        return sha256.hexdigest()
