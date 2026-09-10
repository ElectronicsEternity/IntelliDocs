# ========================================
# File: main.py
# ========================================
#
# Purpose
# -------
# Start the complete IntelliDocs ingestion workflow.
#
# Responsibilities
# ----------------
# - Discover PDF files in the documents folder.
# - Process each PDF through production ingestion.
# - Release workflow resources after processing.
#
# ========================================

from pathlib import Path

from app.ingestion.document_ingestion_workflow import (
    DocumentIngestionWorkflow,
)
from app.ingestion.parser import PDFParser


# ==========================================================
# Configuration
# ==========================================================

DOCUMENTS_FOLDER = Path("documents")
OWNER_ID = "dev_user"


# ==========================================================
# Main Workflow
# ==========================================================

def main() -> None:
    pdf_files = PDFParser.get_pdf_files(
        DOCUMENTS_FOLDER
    )

    # Stop clearly when there is nothing to ingest.
    if not pdf_files:
        print("No PDF files found in documents.")
        return

    workflow = DocumentIngestionWorkflow()

    try:
        # Process files in predictable filename order.
        for pdf_file in pdf_files:
            workflow.process(
                pdf_path=pdf_file,
                owner_id=OWNER_ID,
            )
    finally:
        # Always release the PostgreSQL connection.
        workflow.close()


# ==========================================================
# Entry Point
# ==========================================================

if __name__ == "__main__":
    main()
