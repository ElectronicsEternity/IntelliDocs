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
from app.indexing.page_mapper import PageMapper
from app.ingestion.parser import PDFParser
from app.ingestion.pdf_table_processor import (
    PDFTableProcessor,
)
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
        self.page_mapper = PageMapper(self.node_repository)
        self.table_processor = PDFTableProcessor()

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

        # Stop before paid work when this file already exists.
        if register_document and not self.indexer.register_document(document):
            print("=== Ingestion Skipped ===\n")
            return False

        try:
            # Combine all pages for hierarchy profiling.
            document_text = "\n".join(
                page.text for page in document.pages
            )

            # Ask the profiler for the complete hierarchy.
            hierarchy = self.profiler.generate_hierarchy(
                document_text=document_text,
                document_language=document.language,
                document_id=document.id,
                owner_id=owner_id,
            )

            # Convert hierarchy JSON into database nodes.
            self.importer.import_hierarchy(
                document_id=document.id,
                hierarchy=hierarchy,
            )
            self.indexer.update_document_status(
                document.id,
                DOCUMENT_STATUS_PROFILED,
                owner_id,
            )

            # Locate node pages and character positions.
            self.page_mapper.map_document(document)
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
                pdf_path
            )

            # Build and persist structured retrieval data.
            self.indexer.index_document(
                document=document,
                nodes=nodes,
                normalized_tables=normalized_tables,
            )

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
