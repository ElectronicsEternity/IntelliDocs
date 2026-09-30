# ========================================
# File: document_ingestion_workflow.py
# ========================================
#
# Purpose
# -------
# Coordinate complete document ingestion.
#
# Responsibilities
# ----------------
# - Parse and register one PDF document.
# - Profile and persist its hierarchy.
# - Map hierarchy nodes to physical positions.
# - Process tables and build structured chunks.
# - Persist chunk and node embeddings.
#
# ========================================

from pathlib import Path

from app.config import settings
from app.constants import (
    CURRENT_PAGE_MAPPING_VERSION,
    DOCUMENT_STATUS_FAILED,
    DOCUMENT_STATUS_PROFILED,
)
from app.database.database import Database
from app.indexing.document_indexer import DocumentIndexer
from app.indexing.document_profiler import DocumentProfiler
from app.indexing.hierarchy_importer import HierarchyImporter
from app.indexing.forward_dfs_page_mapper import ForwardDFSPageMapper
from app.ingestion.parser import PDFParser
from app.ingestion.ai_table_processor import AIVisualTableProcessor
from app.repositories.document_node_repository import (
    DocumentNodeRepository,
)


# ==========================================================
# Document Ingestion Workflow
# ==========================================================

class DocumentIngestionWorkflow:

    # Create all production workflow components.
    def __init__(self):
        self.database = Database()
        self.indexer = DocumentIndexer()
        self.profiler = DocumentProfiler()
        self.importer = HierarchyImporter(self.database)
        self.node_repository = DocumentNodeRepository(
            self.database
        )
        self.page_mapper = ForwardDFSPageMapper(self.node_repository)
        self.table_processor = AIVisualTableProcessor()

    # Process one PDF from parsing through embeddings.
    def process(
        self,
        pdf_path: Path,
        owner_id: str,
        document_id: str | None = None,
        register_document: bool = True,
        original_filename: str | None = None,
    ) -> int | bool:
        self.node_repository.owner_id = owner_id
        print(f"\n=== Ingestion Started: {pdf_path.name} ===")

        # Parse pages and construct the document model.
        document = PDFParser(pdf_path).extract_text(
            owner_id=owner_id,
            document_id=document_id,
            original_filename=original_filename,
        )
        if document.total_pages > settings.MAX_PAGES_PER_DOCUMENT:
            raise ValueError("Document exceeds the configured page limit.")
        print(f"Stage parse: {document.total_pages} physical page(s) extracted.")

        # Stop before paid work when this file already exists.
        if register_document and not self.indexer.register_document(document):
            print("=== Ingestion Skipped ===\n")
            return False

        try:
            # Combine all pages for hierarchy profiling.
            page_numbers = [page.page_number for page in document.pages]
            expected_page_numbers = list(range(1, document.total_pages + 1))
            if page_numbers != expected_page_numbers:
                raise ValueError(
                    "Extracted page labels must be unique, ordered and cover "
                    "every physical PDF page."
                )
            document_text = "\n\n".join(
                f"[[PAGE_LABEL: {page.page_number}]]\n{page.text}"
                for page in document.pages
            )

            # Ask the profiler for the complete hierarchy.
            hierarchy = self.profiler.generate_hierarchy(
                document_text=document_text,
                document_language=document.language,
                document_id=document.id,
                owner_id=owner_id,
                page_count=document.total_pages,
            )
            print("Stage hierarchy: validated profile received.")

            # Save document-level routing data before local node mapping. This
            # lets later questions choose likely documents without another AI call.
            self.indexer.store_document_routing_profile(document, hierarchy)
            print("Stage hierarchy: document selection profile stored.")

            # Convert hierarchy JSON into database nodes.
            mapping_metadata = self.importer.import_hierarchy(
                document_id=document.id,
                hierarchy=hierarchy,
                owner_id=owner_id,
            )
            self.indexer.update_document_status(
                document.id,
                DOCUMENT_STATUS_PROFILED,
                owner_id,
            )

            # Locate node pages and character positions.
            mapping_report = self.page_mapper.map_document(
                document,
                page_hints=mapping_metadata["page_hints"],
                opening_texts=mapping_metadata["opening_texts"],
            )
            print(
                "Stage mapping: "
                f"{mapping_report['resolved']} text anchor(s) resolved; "
                f"{len(mapping_report['unresolved'])} node(s) unresolved."
            )
            if mapping_report["resolved"] == 0:
                raise ValueError(
                    "Page mapping resolved 0 searchable hierarchy nodes; "
                    "processing stopped before table extraction."
                )
            self.indexer.update_page_mapping_version(
                document.id,
                CURRENT_PAGE_MAPPING_VERSION,
                owner_id,
            )

            # Reload nodes containing persisted positions.
            nodes = self.node_repository.get_by_document(
                document.id
            )

            # Extract and normalize every physical table.
            normalized_tables = self.table_processor.process(
                pdf_path,
                owner_id=owner_id,
                document_id=document.id,
            )
            print(
                f"Stage tables: {len(normalized_tables)} logical table(s) extracted."
            )

            # The hierarchy pass owns table start pages; the visual table pass
            # owns complete table ranges. Reconcile and persist both before
            # chunk construction so the linker sees the same verified ranges.
            if normalized_tables:
                existing_ids = {node.id for node in nodes}
                existing_sequences = {
                    node.id: node.sequence_no for node in nodes
                }
                self.indexer.table_node_linker.link_tables(
                    normalized_tables=normalized_tables,
                    nodes=nodes,
                )
                synthetic_nodes = [
                    node for node in nodes if node.id not in existing_ids
                ]
                changed_siblings = [
                    node
                    for node in nodes
                    if (
                        node.id in existing_ids
                        and node.sequence_no != existing_sequences[node.id]
                    )
                ]
                if synthetic_nodes:
                    self.node_repository.bulk_create(synthetic_nodes)
                    print(
                        "Stage tables: "
                        f"{len(synthetic_nodes)} standalone table node(s) created."
                    )
                self.node_repository.bulk_update_sequence_numbers(
                    changed_siblings
                )
                self.node_repository.bulk_update_page_ranges(nodes)
                print("Stage tables: hierarchy table ranges reconciled.")

            # Build and persist structured retrieval data.
            self.indexer.index_document(
                document=document,
                nodes=nodes,
                normalized_tables=normalized_tables,
            )
            print("Stage index: chunks and embeddings persisted.")

        # Mark the registered document when processing fails.
        except Exception:
            self.indexer.update_document_status(
                document.id,
                DOCUMENT_STATUS_FAILED,
                owner_id,
            )
            raise

        print(f"=== Ingestion Complete: {pdf_path.name} ===\n")
        return document.total_pages

    # Close resources owned by the workflow.
    def close(self) -> None:
        self.indexer.close()
