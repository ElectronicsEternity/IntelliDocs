import os
# ========================================
# File: hybrid_chunking.py
# ========================================
#
# Purpose
# -------
# Test node and table chunk creation together.
#
# Responsibilities
# ----------------
# - Load real mapped nodes from PostgreSQL.
# - Extract node-owned text scopes.
# - Link logical tables to TABLE nodes.
# - Build chunks without writing to PostgreSQL.
# - Print concise integrity checks.
#
# ========================================

from pathlib import Path

import pdfplumber

from app.database.database import Database
from app.indexing.node_scope_extractor import (
    NodeScopeExtractor,
)
from app.indexing.table_node_linker import TableNodeLinker
from app.ingestion.parser import PDFParser
from app.ingestion.pdfplumber_table_extractor import (
    PdfPlumberTableExtractor,
)
from app.ingestion.table_continuation_merger import (
    TableContinuationMerger,
)
from app.ingestion.table_normalizer import TableNormalizer
from app.rag.chunker import Chunker
from app.rag.chunk_validator import ChunkValidator
from app.repositories.document_node_repository import (
    DocumentNodeRepository,
)


# ==========================================================
# Test Configuration
# ==========================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DOCUMENT_ID = "40cbd327-0728-4803-b0a4-be7e85e52b8d"
PDF_FILE = (
    PROJECT_ROOT
    / "documents"
    / "56. P.U. (A) 2022_140 "
    "Perintah Gaji Minimum 2022.pdf"
)


# ==========================================================
# Test Execution
# ==========================================================

def main() -> None:
    document = PDFParser(PDF_FILE).extract_text(
        owner_id=os.environ["INTELLIDOCS_DEV_USER_ID"]
    )

    # Align parsed content with the persisted hierarchy.
    document.id = DOCUMENT_ID
    repository = DocumentNodeRepository(Database())
    nodes = repository.get_by_document(DOCUMENT_ID)

    scope_extractor = NodeScopeExtractor()
    table_extractor = PdfPlumberTableExtractor()
    merger = TableContinuationMerger()
    normalizer = TableNormalizer()
    linker = TableNodeLinker()
    chunker = Chunker()
    validator = ChunkValidator()

    # Build text scopes from mapped anchors.
    scopes = scope_extractor.extract_node_scopes(
        document=document,
        nodes=nodes,
    )
    text_chunks = chunker.chunk_node_scopes(
        document=document,
        scopes=scopes,
    )

    # Extract physical tables from every PDF page.
    fragments = []
    with pdfplumber.open(PDF_FILE) as pdf_document:
        for page_number, page in enumerate(
            pdf_document.pages,
            start=1,
        ):
            fragments.extend(
                table_extractor.extract_page_tables(
                    page=page,
                    page_number=page_number,
                )
            )

    logical_tables = merger.merge_tables(fragments)
    normalized_tables = [
        normalizer.normalize_logical_table(table)
        for table in logical_tables
    ]
    table_node_ids = linker.link_tables(
        normalized_tables=normalized_tables,
        nodes=nodes,
    )
    table_chunks = chunker.chunk_tables(
        document=document,
        normalized_tables=normalized_tables,
        table_node_ids=table_node_ids,
        starting_chunk_number=len(text_chunks) + 1,
    )
    chunks = chunker.order_chunks_by_hierarchy(
        chunks=text_chunks + table_chunks,
        nodes=nodes,
    )

    # Run reusable production chunk checks.
    result = validator.validate(
        chunks=chunks,
        nodes=nodes,
    )
    table_chunk_numbers = [
        chunk.chunk_number
        for chunk in chunks
        if chunk.content_type == "table"
    ]
    tables_interleaved = (
        bool(table_chunk_numbers)
        and table_chunk_numbers[-1] < len(chunks)
    )

    print("=== Hybrid Chunking Started ===")
    print(f"Nodes loaded: {len(nodes)}")
    print(f"Node scopes: {len(scopes)}")
    print(f"Text chunks: {len(text_chunks)}")
    print(f"Title-only scopes skipped: "
          f"{len(scopes) - len(text_chunks)}")
    print(f"Logical tables: {len(logical_tables)}")
    print(f"Table chunks: {len(table_chunks)}")

    # Show each table's verified hierarchy link.
    for index, table_chunk in enumerate(
        table_chunks,
        start=1,
    ):
        pages = table_chunk.metadata.page_numbers
        print(
            f"Table {index} | pages={list(pages)} | "
            f"node={table_chunk.node_id}"
        )

    print("=== Hybrid Chunking Ended ===")
    print(f"Total chunks: {len(chunks)}")
    print(
        "Valid node links: "
        f"{not result.invalid_node_chunks}"
    )
    print(
        "Sequential numbers: "
        f"{result.sequential_numbers}"
    )
    print(f"Table chunk numbers: {table_chunk_numbers}")
    print(f"Tables interleaved: {tables_interleaved}")
    print(f"Pages in order: {result.pages_in_order}")
    print(f"Chunks valid: {result.is_valid}")
    print("Database writes: False")


# ==========================================================
# Entry Point
# ==========================================================

if __name__ == "__main__":
    main()
