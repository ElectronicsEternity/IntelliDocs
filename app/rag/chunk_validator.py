# ========================================
# File: chunk_validator.py
# ========================================
#
# Purpose
# -------
# Validate hierarchy-based chunks before persistence.
#
# Responsibilities
# ----------------
# - Verify every chunk links to a real node.
# - Verify chunk numbers are consecutive.
# - Verify chunks remain in document page order.
#
# ========================================

from dataclasses import dataclass

from app.models.chunk import Chunk
from app.models.document_node import DocumentNode


# ==========================================================
# Validation Result
# ==========================================================

@dataclass(frozen=True)
class ChunkValidationResult:
    invalid_node_chunks: tuple[Chunk, ...]
    sequential_numbers: bool
    pages_in_order: bool

    @property
    def is_valid(self) -> bool:
        return (
            not self.invalid_node_chunks
            and self.sequential_numbers
            and self.pages_in_order
        )


# ==========================================================
# Chunk Validator
# ==========================================================

class ChunkValidator:

    # Validate the final ordered chunk collection.
    def validate(
        self,
        chunks: list[Chunk],
        nodes: list[DocumentNode],
    ) -> ChunkValidationResult:
        node_ids = {node.id for node in nodes}
        invalid_node_chunks = [
            chunk
            for chunk in chunks
            if chunk.node_id not in node_ids
        ]
        chunk_numbers = [
            chunk.chunk_number for chunk in chunks
        ]
        expected_numbers = list(
            range(1, len(chunks) + 1)
        )
        pages_in_order = all(
            current.page_number
            <= following.page_number
            for current, following in zip(
                chunks,
                chunks[1:],
            )
        )

        return ChunkValidationResult(
            invalid_node_chunks=tuple(
                invalid_node_chunks
            ),
            sequential_numbers=(
                chunk_numbers == expected_numbers
            ),
            pages_in_order=pages_in_order,
        )
