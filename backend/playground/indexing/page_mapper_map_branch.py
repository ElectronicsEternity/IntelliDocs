import os
from pathlib import Path

from app.database.database import Database
from app.indexing.page_mapper import PageMapper
from app.indexing.page_mapping_validator import (
    PageMappingValidator,
)
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


def print_branch(mapper, node, nodes, indent=0):
    # Limit only the terminal display. The real title is unchanged.
    display_title = node.title or "[no title]"

    if len(display_title) > 80:
        display_title = f"{display_title[:80]}..."

    page_result = (
        node.start_page
        if node.start_page is not None
        else "[not mapped]"
    )

    character_result = (
        node.start_character
        if node.start_character is not None
        else "[not mapped]"
    )

    print(
        f"{'  ' * indent}"
        f"{node.node_type} | "
        f"depth={node.depth} | "
        f"sequence={node.sequence_no} | "
        f"start_page={page_result} | "
        f"start_character={character_result} | "
        f"title={display_title}"
    )

    children = mapper._get_children(
        parent_id=node.id,
        nodes=nodes,
    )

    for child in children:
        print_branch(
            mapper=mapper,
            node=child,
            nodes=nodes,
            indent=indent + 1,
        )


def main():
    db = Database()
    repository = DocumentNodeRepository(db)
    mapper = PageMapper(repository)
    validator = PageMappingValidator()

    # Load real DocumentNode records from PostgreSQL.
    nodes = repository.get_by_document(
        TEST_DOCUMENT_ID
    )

    if not nodes:
        print("No DocumentNode records found.")
        return

    # Remember the database values so we can prove this test does not save.
    original_database_ranges = {
        node.id: (node.start_page, node.end_page)
        for node in nodes
    }

    # Reset only these in-memory objects for a clean _map_branch() test.
    # This assignment does not update PostgreSQL.
    for node in nodes:
        node.start_page = None
        node.start_character = None
        node.end_page = None

    parser = PDFParser(PDF_FILE)
    document = parser.extract_text(owner_id=os.environ["INTELLIDOCS_DEV_USER_ID"])

    root_nodes = sorted(
        [node for node in nodes if node.parent_id is None],
        key=lambda node: node.sequence_no,
    )

    print(f"Document ID: {TEST_DOCUMENT_ID}")
    print(f"PDF: {PDF_FILE.name}")
    print(f"Nodes loaded: {len(nodes)}")
    print(f"PDF pages loaded: {document.total_pages}")
    print(f"Root nodes: {len(root_nodes)}")

    print_function_start("PageMapper._map_branch()")

    # Map each root using the complete document as its initial boundary.
    for root_node in root_nodes:
        mapper._map_branch(
            document=document,
            node=root_node,
            nodes=nodes,
            start_page=1,
            end_page=document.total_pages,
        )

    print_function_end("PageMapper._map_branch()")

    titled_nodes = [
        node
        for node in nodes
        if (
            node.node_type.upper() != "TABLE"
            and node.title
            and node.title.strip()
        )
    ]

    mapped_title_count = sum(
        node.start_page is not None
        for node in titled_nodes
    )

    # Validate mapped DFS order through production code.
    boundary_violations = (
        validator.find_physical_order_violations(nodes)
    )

    # Reload fresh objects from PostgreSQL and compare their stored ranges.
    database_nodes_after_test = repository.get_by_document(
        TEST_DOCUMENT_ID
    )

    database_ranges_after_test = {
        node.id: (node.start_page, node.end_page)
        for node in database_nodes_after_test
    }

    database_unchanged = (
        database_ranges_after_test == original_database_ranges
    )

    print("\nResults:")
    print(f"Titles available: {len(titled_nodes)}")
    print(f"Titles mapped: {mapped_title_count}")
    print(
        "Page/character order violations: "
        f"{len(boundary_violations)}"
    )
    print(f"Database unchanged: {database_unchanged}")
    print("\nHierarchy with in-memory start pages:")

    for root_node in root_nodes:
        print_branch(
            mapper=mapper,
            node=root_node,
            nodes=nodes,
        )


if __name__ == "__main__":
    main()
