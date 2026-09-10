# ========================================
# File: chunker.py
# ========================================
#
# Purpose
# -------
# Build searchable chunks from document content.
#
# Responsibilities
# ----------------
# - Preserve legacy page chunking as a fallback.
# - Build one text chunk per meaningful node scope.
# - Build one table chunk per normalized table.
# - Attach node and content-type information.
#
# ========================================

import uuid

from app.constants import CHUNK_OVERLAP, CHUNK_SIZE
from app.models.chunk import Chunk
from app.models.chunk_metadata import (
    TableChunkMetadata,
    TableField,
    TextChunkMetadata,
)
from app.models.document import Document
from app.models.document_node import DocumentNode
from app.rag.tokenizer import Tokenizer


# ==========================================================
# Chunker
# ==========================================================

class Chunker:

    def __init__(self):
        self.tokenizer = Tokenizer()

    # Preserve page slicing for documents without a hierarchy.
    def chunk_document(
        self,
        document: Document,
        chunk_size: int = CHUNK_SIZE,
    ) -> list[Chunk]:
        chunks = []
        chunk_number = 1

        # Process every parsed page independently.
        for page in document.pages:
            tokens = self.tokenizer.encode(page.text)
            step = chunk_size - CHUNK_OVERLAP

            # Split one page using the existing overlap rule.
            for start in range(0, len(tokens), step):
                chunk_tokens = tokens[
                    start:start + chunk_size
                ]
                chunk_text = self.tokenizer.decode(
                    chunk_tokens
                )
                metadata = TextChunkMetadata(
                    page_numbers=(page.page_number,),
                    hierarchy_path=(),
                    start_page=page.page_number,
                    start_character=0,
                    end_page=page.page_number,
                    end_character=len(page.text),
                )
                chunks.append(
                    Chunk(
                        id=str(uuid.uuid4()),
                        document_id=document.id,
                        node_id=None,
                        chunk_number=chunk_number,
                        page_number=page.page_number,
                        content_type="text",
                        text=chunk_text,
                        token_count=len(chunk_tokens),
                        metadata=metadata,
                    )
                )
                chunk_number += 1

        return chunks

    # Build one chunk per meaningful hierarchy-owned scope.
    def chunk_node_scopes(
        self,
        document: Document,
        scopes: list[dict],
        starting_chunk_number: int = 1,
    ) -> list[Chunk]:
        chunks = []
        chunk_number = starting_chunk_number

        # Preserve physical order from the extractor.
        for scope in scopes:
            if self._is_title_only_scope(scope):
                continue

            # Exclude an untouched end page.
            final_page = (
                scope["end_page"]
                if scope["end_character"] > 0
                else max(
                    scope["start_page"],
                    scope["end_page"] - 1,
                )
            )
            page_numbers = tuple(
                range(
                    scope["start_page"],
                    final_page + 1,
                )
            )
            hierarchy_path = tuple(
                scope.get("hierarchy_path", ())
            )
            metadata = TextChunkMetadata(
                page_numbers=page_numbers,
                hierarchy_path=hierarchy_path,
                start_page=scope["start_page"],
                start_character=scope["start_character"],
                end_page=scope["end_page"],
                end_character=scope["end_character"],
            )
            chunk_text = self._build_scope_text(
                document=document,
                scope=scope,
            )
            chunks.append(
                Chunk(
                    id=str(uuid.uuid4()),
                    document_id=document.id,
                    node_id=scope["node_id"],
                    chunk_number=chunk_number,
                    page_number=scope["start_page"],
                    content_type="text",
                    text=chunk_text,
                    token_count=(
                        self.tokenizer.count_tokens(
                            chunk_text
                        )
                    ),
                    metadata=metadata,
                )
            )
            chunk_number += 1

        return chunks

    # Build one retrieval chunk per normalized table.
    def chunk_tables(
        self,
        document: Document,
        normalized_tables: list[dict],
        table_node_ids: list[str] | None = None,
        starting_chunk_number: int = 1,
    ) -> list[Chunk]:
        if (
            table_node_ids is not None
            and len(table_node_ids) != len(normalized_tables)
        ):
            raise ValueError(
                "Each table requires one matching node ID."
            )

        chunks = []
        chunk_number = starting_chunk_number

        # Process logical tables in document order.
        for table_index, table in enumerate(
            normalized_tables
        ):
            table_number = table_index + 1
            page_numbers = table.get("page_numbers", [])
            fields = self._build_table_fields(table)

            # Do not create an empty retrieval chunk.
            if not fields:
                continue

            metadata = TableChunkMetadata(
                page_numbers=tuple(page_numbers),
                table_number=table_number,
                row_count=table["row_count"],
                column_count=table["column_count"],
                fields=fields,
            )
            chunk_text = self._build_table_text(
                document=document,
                metadata=metadata,
            )
            page_number = (
                page_numbers[0] if page_numbers else 1
            )
            node_id = (
                table_node_ids[table_index]
                if table_node_ids is not None
                else None
            )
            chunks.append(
                Chunk(
                    id=str(uuid.uuid4()),
                    document_id=document.id,
                    node_id=node_id,
                    chunk_number=chunk_number,
                    page_number=page_number,
                    content_type="table",
                    text=chunk_text,
                    token_count=(
                        self.tokenizer.count_tokens(
                            chunk_text
                        )
                    ),
                    metadata=metadata,
                )
            )
            chunk_number += 1

        return chunks

    # Sort node-linked chunks in hierarchy DFS order.
    def order_chunks_by_hierarchy(
        self,
        chunks: list[Chunk],
        nodes: list[DocumentNode],
    ) -> list[Chunk]:
        node_order = self._build_node_order(nodes)
        node_positions = {
            node_id: position
            for position, node_id in enumerate(node_order)
        }
        fallback_position = len(node_positions)

        # Retain creation order for chunks sharing one node.
        indexed_chunks = list(enumerate(chunks))

        # Return a safe position when a chunk has no node.
        def get_chunk_position(
            item: tuple[int, Chunk],
        ) -> tuple[int, int]:
            original_position, chunk = item

            if chunk.node_id is None:
                return fallback_position, original_position

            hierarchy_position = node_positions.get(
                chunk.node_id,
                fallback_position,
            )
            return hierarchy_position, original_position

        indexed_chunks.sort(
            key=get_chunk_position
        )
        ordered_chunks = [
            chunk for _, chunk in indexed_chunks
        ]

        # Number the final order from one for this document.
        for chunk_number, chunk in enumerate(
            ordered_chunks,
            start=1,
        ):
            chunk.chunk_number = chunk_number

        return ordered_chunks

    # Build parent-first DFS order using sibling sequence.
    def _build_node_order(
        self,
        nodes: list[DocumentNode],
    ) -> list[str]:
        children_by_parent = {}

        # Group nodes under their direct parent.
        for node in nodes:
            children_by_parent.setdefault(
                node.parent_id,
                [],
            ).append(node)

        # Apply sequence only within each sibling group.
        for children in children_by_parent.values():
            children.sort(
                key=lambda child: child.sequence_no
            )

        ordered_node_ids = []
        visited_node_ids = set()

        # Visit each parent before its children.
        def visit(node: DocumentNode) -> None:
            if node.id in visited_node_ids:
                return

            visited_node_ids.add(node.id)
            ordered_node_ids.append(node.id)

            for child in children_by_parent.get(node.id, []):
                visit(child)

        # Start DFS from every root in sibling order.
        for root in children_by_parent.get(None, []):
            visit(root)

        # Keep malformed orphan nodes visible at the end.
        for node in sorted(
            nodes,
            key=lambda item: (
                item.depth,
                item.sequence_no,
            ),
        ):
            visit(node)

        return ordered_node_ids

    # Detect scopes containing only their title or identifier.
    def _is_title_only_scope(self, scope: dict) -> bool:
        content = " ".join(scope["text"].split()).lower()
        anchor = " ".join(
            scope["anchor_text"].split()
        ).lower()
        return content == anchor

    # Add source and hierarchy terms to searchable scope text.
    def _build_scope_text(
        self,
        document: Document,
        scope: dict,
    ) -> str:
        parts = [f"Document: {document.title}"]
        hierarchy_path = scope.get("hierarchy_path", ())

        if hierarchy_path:
            parts.append(
                "Hierarchy: " + " > ".join(hierarchy_path)
            )

        parts.append(scope["text"].strip())
        return "\n".join(parts)

    # Convert normalized geometry into embedding text.
    def _build_table_text(
        self,
        document: Document,
        metadata: TableChunkMetadata,
    ) -> str:
        pages = ", ".join(map(str, metadata.page_numbers))
        parts = [
            f"Document: {document.title}",
            f"Table number: {metadata.table_number}",
            f"Pages: {pages}",
        ]

        # Describe every logical row from left to right.
        for row_number in range(
            1,
            metadata.row_count + 1,
        ):
            row_fields = [
                field
                for field in metadata.fields
                if (
                    field.row_start <= row_number
                    <= field.row_end
                    and field.value
                )
            ]
            row_fields.sort(
                key=lambda field: field.column_start
            )
            row_values = [
                "columns "
                f"{field.column_start}-{field.column_end}: "
                f"{field.value}"
                for field in row_fields
            ]

            if row_values:
                parts.append(
                    f"Row {row_number}: "
                    f"{'; '.join(row_values)}"
                )

        return ". ".join(parts) + "."

    # Convert normalized cells into table field models.
    def _build_table_fields(
        self,
        table: dict,
    ) -> list[TableField]:
        return [
            TableField(
                value=cell["value"],
                row_start=cell["row_start"],
                row_end=cell["row_end"],
                column_start=cell["column_start"],
                column_end=cell["column_end"],
                source_page=cell["source_page"],
                source_table=cell["source_table"],
            )
            for cell in table["cells"]
        ]
