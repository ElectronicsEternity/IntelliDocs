# ========================================
# File: chunk.py
# ========================================
#
# Purpose
# -------
# Represent one searchable document chunk.
#
# Responsibilities
# ----------------
# - Store text used for embedding.
# - Link the chunk to its document and node.
# - Identify whether content is text or a table.
# - Preserve content-specific metadata.
#
# ========================================

from dataclasses import dataclass

from app.models.chunk_metadata import ChunkMetadata


# ==========================================================
# Chunk
# ==========================================================

@dataclass
class Chunk:
    id: str
    document_id: str
    node_id: str | None
    chunk_number: int
    page_number: int
    content_type: str
    text: str
    token_count: int
    metadata: ChunkMetadata
