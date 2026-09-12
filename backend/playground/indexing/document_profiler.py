import os
# ========================================
# File: test_document_profiler.py
# ========================================

import json

from pathlib import Path

from app.ingestion.parser import PDFParser
from app.indexing.document_profiler import (
    DocumentProfiler
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]

PDF_FILE = (
    PROJECT_ROOT
    / "documents"
    / "56. P.U. (A) 2022_140 "
    "Perintah Gaji Minimum 2022.pdf"
)

OUTPUT_FILE = (
    PROJECT_ROOT
    / "outputs"
    / "document_profiler_output.txt"
)


def main():

    print(
        "Starting DocumentProfiler"
    )

    parser = PDFParser(
        PDF_FILE
    )

    document = parser.extract_text(
        owner_id=os.environ["INTELLIDOCS_DEV_USER_ID"]
    )

    print(
        f"Detected language: "
        f"{document.language}"
    )

    document_text = "\n".join(
        page.text
        for page in document.pages
    )

    profiler = DocumentProfiler()

    hierarchy = (
        profiler.generate_hierarchy(
            document_text=document_text,
            document_language=(
                document.language
            ),
            document_id=document.id,
            owner_id=os.environ["INTELLIDOCS_DEV_USER_ID"],
        )
    )

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            hierarchy,
            file,
            indent=2,
            ensure_ascii=False
        )

    print(
        f"Profile saved: "
        f"{OUTPUT_FILE}"
    )


if __name__ == "__main__":

    main()
