# ========================================
# File: parser_interface.py
# ========================================
#
# Purpose
# -------
# Define the common contract used by every PDF parser adapter.
#
# Responsibilities
# ----------------
# - Accept a PDF file path.
# - Extract every page from the PDF.
# - Return pages using the IntelliDocs Page model.
#
# ========================================

# Import the abstract class tools used to define the parser contract.
from abc import ABC, abstractmethod

# Import Path so every adapter receives the same file path type.
from pathlib import Path

# Import the shared Page model returned by every adapter.
from app.models.page import Page


# ==========================================================
# PDF Parser Interface
# ==========================================================

# Require every PDF parser adapter to provide the same method.
class PDFParserInterface(ABC):

    # Require adapters to extract all PDF pages into Page objects.
    @abstractmethod
    def extract_pages(self, pdf_path: Path) -> list[Page]:
        """Extract and return every page from the supplied PDF file."""

        # Abstract methods contain no library-specific implementation.
        raise NotImplementedError
