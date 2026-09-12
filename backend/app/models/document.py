# Import dataclass decorator to automatically generate class methods
from dataclasses import dataclass

from datetime import datetime

from app.models.page import Page


# Represents a complete document uploaded into IntelliDocs
@dataclass
class Document:
    # ==============================
    # File Metadata
    # ==============================

    # Unique document identifier
    id: str
    # Original filename
    filename: str
    # File extension (e.g. pdf)
    file_extension: str
    # File size in bytes
    file_size: int
    # SHA256 hash used to detect duplicate files
    file_hash: str
    # Date and time the document was uploaded
    uploaded_at: datetime

    # ==============================
    # Document Metadata
    # ==============================
    # Human readable title
    title: str
    # Number of pages
    total_pages: int
    # Language of the document
    language: str
    # Country / Region
    jurisdiction: str
    # Type of document
    # Publisher / Source
    publisher: str

    # ==============================
    # Processing Metadata
    # ==============================

    # Processing duration in milliseconds
    processing_time_ms: int
    # Embedding model used
    embedding_model: str

    # ==============================
    # Document Content
    # ==============================
    # List containing every page in the document
    pages: list[Page]

    # Date and time indexing completed
    indexed_at: datetime | None = None

    # Owner of the document
    owner_id: str | None = None

    document_type: str | None = None