import os
# ========================================
# File: document_language_test.py
# ========================================

from pathlib import Path

from app.ingestion.parser import PDFParser
from app.storage.postgres_vector_store import (
    PostgresVectorStore
)


PDF_FILE = Path(
    r"C:\Users\elect\Documents\PRANOVA\intellidocs\documents\56. P.U. (A) 2022_140 Perintah Gaji Minimum 2022.pdf"
)

OWNER_ID = os.environ["INTELLIDOCS_DEV_USER_ID"]


def main():

    print("Starting Test...")

    parser = PDFParser(
        PDF_FILE
    )

    document = parser.extract_text(
        owner_id=OWNER_ID
    )

    print(
        f"Detected language: "
        f"{document.language}"
    )

    store = PostgresVectorStore()

    store.add_document(
        document
    )

    print(
        "Document inserted."
    )


if __name__ == "__main__":

    main()