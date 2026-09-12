import os
# ========================================
# File: production_validation_dry_run.py
# ========================================
#
# Purpose
# -------
# Test production validators without database writes.
#
# Responsibilities
# ----------------
# - Load the previously approved raw profile.
# - Build and map hierarchy nodes in memory.
# - Validate hierarchy, scopes, and chunks.
# - Avoid every repository write method.
#
# ========================================

import json

from pathlib import Path

from app.indexing.document_profile_validator import (
    DocumentProfileValidator,
)
from app.indexing.hierarchy_importer import (
    HierarchyImporter,
)
from app.indexing.hierarchy_validator import (
    HierarchyValidator,
)
from app.indexing.node_scope_extractor import (
    NodeScopeExtractor,
)
from app.indexing.node_scope_validator import (
    NodeScopeValidator,
)
from app.indexing.page_mapper import PageMapper
from app.indexing.page_mapping_validator import (
    PageMappingValidator,
)
from app.indexing.table_node_linker import TableNodeLinker
from app.ingestion.parser import PDFParser
from app.ingestion.pdf_table_processor import (
    PDFTableProcessor,
)
from app.rag.chunker import Chunker
from app.rag.chunk_validator import ChunkValidator


# ==========================================================
# Test Files
# ==========================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PDF_FILE = (
    PROJECT_ROOT
    / "documents"
    / "56. P.U. (A) 2022_140 "
    "Perintah Gaji Minimum 2022.pdf"
)
PROFILE_FILE = (
    PROJECT_ROOT
    / "outputs"
    / "document_profiler_output.txt"
)
DRY_RUN_DOCUMENT_ID = "validation-dry-run"


# ==========================================================
# Dry Run
# ==========================================================

def main() -> None:

    # Read the approved profiler response as text.
    hierarchy = json.loads(
        PROFILE_FILE.read_text(encoding="utf-8")
    )
    # Validate raw JSON before creating any node models.
    profile_result = (
        DocumentProfileValidator().validate(
            hierarchy=hierarchy,
            expected_language=hierarchy["language"],
        )
    )

    # Stop immediately when the raw profile is unsafe.
    if not profile_result.is_valid:
        raise ValueError(profile_result.errors)

    # Build nodes without calling repository persistence.
    importer = HierarchyImporter(db=None)

    # Convert valid JSON into unsaved DocumentNode objects.
    nodes = importer.build_nodes(
        document_id=DRY_RUN_DOCUMENT_ID,
        hierarchy=hierarchy,
    )
    # PageMapper private functions need no repository here.
    mapper = PageMapper(repository=None)

    # Build the same lookup used by production PageMapper.
    node_lookup = mapper._build_node_lookup(nodes)

    # Collect the actual child lists returned by PageMapper.
    children_by_parent = {}

    # Test child retrieval separately for every node.
    for node in nodes:
        children_by_parent[node.id] = (
            mapper._get_children(node.id, nodes)
        )

    # Validate lookup, relationships, depth, and sequence.
    hierarchy_result = HierarchyValidator().validate(
        nodes=nodes,
        node_lookup=node_lookup,
        children_by_parent=children_by_parent,
    )

    # Parse and map the real PDF only in memory.
    document = PDFParser(PDF_FILE).extract_text(
        owner_id=os.environ["INTELLIDOCS_DEV_USER_ID"]
    )
    # Link parsed content to the temporary in-memory nodes.
    document.id = DRY_RUN_DOCUMENT_ID

    # Locate roots and preserve their declared sequence.
    root_nodes = sorted(
        [node for node in nodes if node.parent_id is None],
        key=lambda node: node.sequence_no,
    )

    # Map titled branches without calling map_document().
    for root in root_nodes:
        mapper._map_branch(
            document=document,
            node=root,
            nodes=nodes,
            start_page=1,
            end_page=document.total_pages,
        )

    # Map untitled nodes through their identifiers.
    mapper._map_identifier_nodes(
        document=document,
        nodes=nodes,
    )
    # Calculate ranges without calling the saving method.
    mapper._calculate_page_ranges(
        nodes=nodes,
        node_lookup=node_lookup,
        document=document,
    )
    # Validate all calculated positions and ranges.
    mapping_result = PageMappingValidator().validate(
        document=document,
        nodes=nodes,
    )

    # Extract and validate all non-overlapping text scopes.
    scopes = NodeScopeExtractor().extract_node_scopes(
        document=document,
        nodes=nodes,
    )
    # Check scope anchors, content, and boundaries.
    scope_result = NodeScopeValidator().validate(scopes)

    # Build normalized tables and hierarchy-based chunks.
    normalized_tables = PDFTableProcessor().process(
        PDF_FILE
    )
    # Connect each detected table to its hierarchy node.
    table_node_ids = TableNodeLinker().link_tables(
        normalized_tables=normalized_tables,
        nodes=nodes,
    )
    # Create hierarchy-owned text and table chunks.
    chunker = Chunker()
    text_chunks = chunker.chunk_node_scopes(
        document=document,
        scopes=scopes,
    )
    table_chunks = chunker.chunk_tables(
        document=document,
        normalized_tables=normalized_tables,
        table_node_ids=table_node_ids,
    )
    # Put both chunk types into original document order.
    chunks = chunker.order_chunks_by_hierarchy(
        chunks=text_chunks + table_chunks,
        nodes=nodes,
    )
    # Validate node links, numbering, and page order.
    chunk_result = ChunkValidator().validate(
        chunks=chunks,
        nodes=nodes,
    )

    # Display only the final validation summary here.
    print("\n=== Production Validation Dry Run ===")
    print(f"Raw profile valid: {profile_result.is_valid}")
    print(f"Hierarchy valid: {hierarchy_result.is_valid}")
    print(f"Page mapping valid: {mapping_result.is_valid}")
    print(f"Node scopes valid: {scope_result.is_valid}")
    print(f"Chunks valid: {chunk_result.is_valid}")
    print(f"Text scopes: {len(scopes)}")
    print(f"Normalized tables: {len(normalized_tables)}")
    print(f"Final chunks: {len(chunks)}")
    print("Database writes: False")

    # Require every production validation stage to pass.
    all_valid = all(
        (
            profile_result.is_valid,
            hierarchy_result.is_valid,
            mapping_result.is_valid,
            scope_result.is_valid,
            chunk_result.is_valid,
        )
    )

    # Fail visibly instead of hiding a broken stage.
    if not all_valid:
        raise ValueError(
            "One or more production validations failed."
        )


# ==========================================================
# Entry Point
# ==========================================================

if __name__ == "__main__":
    main()
