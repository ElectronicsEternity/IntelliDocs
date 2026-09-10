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


def print_function_start(function_name):
    print("\n" + "=" * 60)
    print(f"START: {function_name}")
    print("=" * 60)


def print_function_end(function_name):
    print("=" * 60)
    print(f"END: {function_name}")
    print("=" * 60)


def main():
    # Use the real hierarchy records from PostgreSQL.
    db = Database()
    repository = DocumentNodeRepository(db)
    mapper = PageMapper(repository)

    nodes = repository.get_by_document(TEST_DOCUMENT_ID)

    if not nodes:
        print("No DocumentNode records found.")
        return

    # Use the real extracted text so the character positions can be checked
    # against exactly what PageMapper receives from the PDF parser.
    parser = PDFParser(PDF_FILE)
    document = parser.extract_text(owner_id="dev_user")

    pages_by_number = {
        page.page_number: page
        for page in document.pages
    }

    titled_nodes = [
        node
        for node in nodes
        if node.title and node.title.strip()
    ]

    found_positions = []

    print(f"Document ID: {TEST_DOCUMENT_ID}")
    print(f"PDF: {PDF_FILE.name}")
    print(f"Titles to search: {len(titled_nodes)}")

    print_function_start("PageMapper._find_title_page()")

    for node in titled_nodes:
        title_position = mapper._find_title_page(
            title=node.title,
            pages=document.pages,
            start_page=1,
            end_page=document.total_pages,
        )

        if title_position is None:
            continue

        page_number = title_position["page_number"]
        start_character = title_position["start_character"]
        page = pages_by_number[page_number]

        # Show original PDF text beginning exactly at the returned character.
        # Whitespace is shortened only for readable terminal output.
        original_text_sample = " ".join(
            page.text[
                start_character:start_character + 120
            ].split()
        )

        found_positions.append(title_position)

        print(
            f"VERIFY | page={page_number} | "
            f"start_character={start_character} | "
            f"original_text='{original_text_sample}'"
        )

    print_function_end("PageMapper._find_title_page()")

    print("\nResults:")
    print(f"Titles searched: {len(titled_nodes)}")
    print(f"Positions found: {len(found_positions)}")
    print(
        f"Positions not found: "
        f"{len(titled_nodes) - len(found_positions)}"
    )
    print("Database unchanged: True")


if __name__ == "__main__":
    main()
