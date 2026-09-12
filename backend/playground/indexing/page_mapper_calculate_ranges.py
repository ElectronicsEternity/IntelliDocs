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
    # Shorten only the displayed title. The real title is unchanged.
    display_title = node.title or "[no title]"

    if len(display_title) > 80:
        display_title = f"{display_title[:80]}..."

    start_page = (
        node.start_page
        if node.start_page is not None
        else "-"
    )

    end_page = (
        node.end_page
        if node.end_page is not None
        else "-"
    )

    print(
        f"{'  ' * indent}"
        f"{node.node_type} | "
        f"depth={node.depth} | "
        f"sequence={node.sequence_no} | "
        f"range={start_page}-{end_page} | "
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

    # Load real hierarchy records from PostgreSQL.
    nodes = repository.get_by_document(
        TEST_DOCUMENT_ID
    )

    if not nodes:
        print("No DocumentNode records found.")
        return

    # Record existing database ranges before changing the in-memory objects.
    original_database_ranges = {}

    for node in nodes:
        original_database_ranges[node.id] = (
            node.start_page,
            node.end_page,
        )

    # Reset only the Python objects so this test starts with empty ranges.
    for node in nodes:
        node.start_page = None
        node.end_page = None

    parser = PDFParser(PDF_FILE)
    document = parser.extract_text(owner_id=os.environ["INTELLIDOCS_DEV_USER_ID"])

    node_lookup = mapper._build_node_lookup(nodes)

    root_nodes = sorted(
        [node for node in nodes if node.parent_id is None],
        key=lambda node: node.sequence_no,
    )

    print(f"Document ID: {TEST_DOCUMENT_ID}")
    print(f"PDF: {PDF_FILE.name}")
    print(f"Nodes loaded: {len(nodes)}")
    print(f"PDF pages loaded: {document.total_pages}")

    # SETUP: _calculate_page_ranges() requires mapped start pages.
    print_function_start("SETUP: PageMapper._map_branch()")

    for root_node in root_nodes:
        mapper._map_branch(
            document=document,
            node=root_node,
            nodes=nodes,
            start_page=1,
            end_page=document.total_pages,
        )

    print_function_end("SETUP: PageMapper._map_branch()")

    # TEST 4: Calculate end pages using siblings and parent boundaries.
    print_function_start("PageMapper._calculate_page_ranges()")

    mapper._calculate_page_ranges(
        nodes=nodes,
        node_lookup=node_lookup,
        document=document,
    )

    print_function_end("PageMapper._calculate_page_ranges()")

    # Run all mapping checks through production code.
    result = validator.validate(
        document=document,
        nodes=nodes,
    )
    incomplete_ranges = result.incomplete_range_nodes
    complete_count = len(nodes) - len(incomplete_ranges)

    # Reload fresh database objects to prove this test did not persist ranges.
    database_nodes_after_test = repository.get_by_document(
        TEST_DOCUMENT_ID
    )

    database_ranges_after_test = {}

    for node in database_nodes_after_test:
        database_ranges_after_test[node.id] = (
            node.start_page,
            node.end_page,
        )

    database_unchanged = (
        database_ranges_after_test == original_database_ranges
    )

    print("\nResults:")
    print(f"Complete ranges: {complete_count}")
    print(f"Incomplete ranges: {len(incomplete_ranges)}")
    print(
        "Invalid ranges: "
        f"{len(result.invalid_range_nodes)}"
    )
    print(
        "Parent range violations: "
        f"{len(result.parent_range_violations)}"
    )
    print(f"Database unchanged: {database_unchanged}")
    print("\nHierarchy with calculated page ranges:")

    for root_node in root_nodes:
        print_branch(
            mapper=mapper,
            node=root_node,
            nodes=nodes,
        )


if __name__ == "__main__":
    main()
