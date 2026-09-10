# ========================================
# File: document_analysis.py
# ========================================

from dataclasses import dataclass

from datetime import datetime

from typing import Optional


@dataclass
class DocumentAnalysis:

    # Parent document
    document_id: str

    # Owner
    owner_id: str

    # SHA256 hash
    file_hash: str

    # Processing status
    processing_status: str


    # Audit
    created_at: datetime
    updated_at: datetime

    # Chunk analyzer output
    recommended_chunk_size: Optional[int]

    # Processing logic versions successfully applied to this document.
    # None means the processing stage has not completed yet.
    page_mapping_version: Optional[int] = None
    chunking_version: Optional[int] = None
    embedding_version: Optional[int] = None
