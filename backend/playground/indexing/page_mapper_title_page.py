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


def print_function_start(function_name):
    # Clearly mark where a function test begins in the terminal.
    print("\n" + "=" * 60)
    print(f"START: {function_name}")
    print("=" * 60)


def print_function_end(function_name):
    # Clearly mark where a function test finishes in the terminal.
    print("=" * 60)
    print(f"END: {function_name}")
    print("=" * 60)


def print_branch(mapper, node, nodes, matched_pages, indent=0):
    # Limit only the displayed title. The real node title is unchanged.
    display_title = node.title or "[no title]"

    if len(display_title) > 80:
        display_title = f"{display_title[:80]}..."

    # Titleless nodes are intentionally skipped by _find_title_page().
    if not node.title or not node.title.strip():
        page_result = "[not searched]"
    else:
        page_number = matched_pages.get(node.id)
        page_result = page_number if page_number is not None else "[not found]"

    print(
        f"{'  ' * indent}"
        f"{node.node_type} | "
        f"depth={node.depth} | "
        f"sequence={node.sequence_no} | "
        f"title={display_title} | "
        f"matched_page={page_result}"
    )

    # _get_children() is used only to display the results as a hierarchy.
    children = mapper._get_children(
        parent_id=node.id,
        nodes=nodes,
    )

    for child in children:
        print_branch(
            mapper=mapper,
            node=child,
            nodes=nodes,
            matched_pages=matched_pages,
            indent=indent + 1,
        )


def main():
    # Load real hierarchy nodes from PostgreSQL.
    db = Database()
    repository = DocumentNodeRepository(db)
    mapper = PageMapper(repository)

    nodes = repository.get_by_document(
        TEST_DOCUMENT_ID
    )

    if not nodes:
        print("No DocumentNode records found.")
        return

    # Extract real page text from the PDF.
    parser = PDFParser(PDF_FILE)
    document = parser.extract_text(owner_id=os.environ["INTELLIDOCS_DEV_USER_ID"])

    print(f"Document ID: {TEST_DOCUMENT_ID}")
    print(f"PDF: {PDF_FILE.name}")
    print(f"Nodes loaded: {len(nodes)}")
    print(f"PDF pages loaded: {document.total_pages}")

    matched_pages = {}

    print_function_start("PageMapper._find_title_page()")

    # Search the complete PDF for every node that has a title.
    for node in nodes:
        if not node.title or not node.title.strip():
            continue

        title_position = mapper._find_title_page(
            title=node.title,
            pages=document.pages,
            start_page=1,
            end_page=document.total_pages,
        )

        # Store the result for display without changing node.start_page.
        matched_pages[node.id] = (
            title_position["page_number"]
            if title_position is not None
            else None
        )

    print_function_end("PageMapper._find_title_page()")

    titles_found = sum(
        page_number is not None
        for page_number in matched_pages.values()
    )

    print("\nResults:")
    print(f"Titles searched: {len(matched_pages)}")
    print(f"Titles found: {titles_found}")
    print(f"Titles not found: {len(matched_pages) - titles_found}")
    print("\nHierarchy with matched pages:")

    root_nodes = sorted(
        [node for node in nodes if node.parent_id is None],
        key=lambda node: node.sequence_no,
    )

    for root_node in root_nodes:
        print_branch(
            mapper=mapper,
            node=root_node,
            nodes=nodes,
            matched_pages=matched_pages,
        )


if __name__ == "__main__":
    main()
