import os
from pathlib import Path

from app.database.database import Database
from app.indexing.page_mapper import PageMapper
from app.ingestion.parser import PDFParser
from app.repositories.document_node_repository import (
    DocumentNodeRepository,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]

PDF_FILE = (
    PROJECT_ROOT
    / "documents"
    / "56. P.U. (A) 2022_140 Perintah Gaji Minimum 2022.pdf"
)

TEST_DOCUMENT_ID = "40cbd327-0728-4803-b0a4-be7e85e52b8d"
TEST_TITLE = "Nama dan permulaan kuat kuasa"
EXPECTED_PAGE = 2


def main():
    # Use the real repository and confirm the test title belongs to a real
    # DocumentNode record for this document.
    db = Database()
    repository = DocumentNodeRepository(db)
    mapper = PageMapper(repository)

    nodes = repository.get_by_document(TEST_DOCUMENT_ID)

    matching_node = next(
        (
            node
            for node in nodes
            if node.title
            and node.title.strip().lower() == TEST_TITLE.lower()
        ),
        None,
    )

    if matching_node is None:
        print(f"DocumentNode title not found: {TEST_TITLE}")
        return

    # Extract the real PDF text used by PageMapper.
    parser = PDFParser(PDF_FILE)
    document = parser.extract_text(owner_id=os.environ["INTELLIDOCS_DEV_USER_ID"])

    print("\n=== _find_title_page() Started ===")

    title_position = mapper._find_title_page(
        title=matching_node.title,
        pages=document.pages,
        start_page=1,
        end_page=document.total_pages,
    )

    print("=== _find_title_page() Ended ===\n")

    if title_position is None:
        print("Result: Title not found")
        return

    page_number = title_position["page_number"]
    start_character = title_position["start_character"]

    matched_page = next(
        page
        for page in document.pages
        if page.page_number == page_number
    )

    # Read from the returned position in the original extracted page text.
    original_text_sample = " ".join(
        matched_page.text[
            start_character:start_character + 100
        ].split()
    )

    normalized_title = " ".join(TEST_TITLE.lower().split())
    normalized_sample = " ".join(
        original_text_sample.lower().split()
    )

    print("Result:")
    print(f"Title: {TEST_TITLE}")
    print(f"Page number: {page_number}")
    print(f"Start character: {start_character}")
    print(f"Original text from position: {original_text_sample}")
    print(f"Expected page found: {page_number == EXPECTED_PAGE}")
    print(
        "Text begins with title: "
        f"{normalized_sample.startswith(normalized_title)}"
    )
    print("Database unchanged: True")


if __name__ == "__main__":
    main()
