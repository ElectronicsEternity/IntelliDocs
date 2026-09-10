# ========================================
# File: chunk_metadata.py
# ========================================
#
# Purpose
# -------
# Store metadata that is specific to one chunk.
#
# Responsibilities
# ----------------
# - Preserve node-scope boundaries.
# - Preserve the node hierarchy path.
# - Preserve normalized table geometry.
#
# ========================================

from dataclasses import dataclass


# ==========================================================
# Table Field
# ==========================================================

# Store one geometry-owned table cell.
@dataclass
class TableField:
    value: str
    row_start: int
    row_end: int
    column_start: int
    column_end: int
    source_page: int
    source_table: int


# ==========================================================
# Text Chunk Metadata
# ==========================================================

# Store physical boundaries for one node-owned text chunk.
@dataclass
class TextChunkMetadata:
    page_numbers: tuple[int, ...]
    hierarchy_path: tuple[str, ...]
    start_page: int
    start_character: int
    end_page: int
    end_character: int


# ==========================================================
# Table Chunk Metadata
# ==========================================================

# Store normalized geometry for one logical table chunk.
@dataclass
class TableChunkMetadata:
    page_numbers: tuple[int, ...]
    table_number: int
    row_count: int
    column_count: int
    fields: list[TableField]


# Allow Chunk to hold either supported metadata model.
ChunkMetadata = TextChunkMetadata | TableChunkMetadata
