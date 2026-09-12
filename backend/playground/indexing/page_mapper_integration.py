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


def print_branch(mapper, node, nodes, indent=0):
    # Shorten only the terminal display. The database title is unchanged.
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

    start_character = (
        node.start_character
        if node.start_character is not None
        else "-"
    )

    print(
        f"{'  ' * indent}"
        f"{node.node_type} | "
        f"depth={node.depth} | "
        f"sequence={node.sequence_no} | "
        f"saved_start={start_page}:{start_character} | "
        f"saved_range={start_page}-{end_page} | "
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

    existing_nodes = repository.get_by_document(
        TEST_DOCUMENT_ID
    )

    if not existing_nodes:
        print("No DocumentNode records found.")
        return

    parser = PDFParser(PDF_FILE)
    document = parser.extract_text(owner_id=os.environ["INTELLIDOCS_DEV_USER_ID"])

    document.id = TEST_DOCUMENT_ID

    print("WARNING: This integration test updates PostgreSQL.")
    print(f"Document ID: {document.id}")
    print(f"PDF: {PDF_FILE.name}")
    print(f"Nodes before mapping: {len(existing_nodes)}")
    print(f"PDF pages loaded: {document.total_pages}")

    # Full workflow:
    # load nodes -> map starts -> calculate ranges -> save ranges.
    mapper.map_document(document)

    # Reload fresh objects to verify what was actually saved in PostgreSQL.
    persisted_nodes = repository.get_by_document(
        TEST_DOCUMENT_ID
    )

    # Validate persisted mapping through production code.
    result = validator.validate(
        document=document,
        nodes=persisted_nodes,
    )
    anchored_nodes = [
        node
        for node in persisted_nodes
        if (
            node.node_type.upper() != "TABLE"
            and (
                (node.title or "").strip()
                or (node.identifier or "").strip()
            )
        )
    ]
    anchored_with_positions = [
        node
        for node in anchored_nodes
        if (
            node.start_page is not None
            and node.start_character is not None
        )
    ]
    complete_count = (
        len(persisted_nodes)
        - len(result.incomplete_range_nodes)
    )

    root_nodes = sorted(
        [
            node
            for node in persisted_nodes
            if node.parent_id is None
        ],
        key=lambda node: node.sequence_no,
    )

    print("\nPersisted database results:")
    print(f"Nodes reloaded: {len(persisted_nodes)}")
    print(f"Complete saved ranges: {complete_count}")
    print(
        "Incomplete saved ranges: "
        f"{len(result.incomplete_range_nodes)}"
    )
    print(
        "Invalid saved ranges: "
        f"{len(result.invalid_range_nodes)}"
    )
    print(
        "Parent range violations: "
        f"{len(result.parent_range_violations)}"
    )
    print(
        "Parent position violations: "
        f"{len(result.parent_position_violations)}"
    )
    print(f"Text-anchored nodes: {len(anchored_nodes)}")
    print(
        "Anchors with saved positions: "
        f"{len(anchored_with_positions)}"
    )
    print(
        "Missing anchor positions: "
        f"{len(result.missing_anchor_nodes)}"
    )
    print(
        "Anchor text mismatches: "
        f"{len(result.anchor_text_mismatches)}"
    )
    print(
        "Physical order violations: "
        f"{len(result.order_violations)}"
    )
    print(
        "TABLE character violations: "
        f"{len(result.table_character_violations)}"
    )
    print(
        "Unanchored nodes with unexpected characters: "
        f"{len(result.unanchored_character_nodes)}"
    )
    print(f"Page mapping valid: {result.is_valid}")
    print("\nHierarchy with persisted page and character positions:")

    for root_node in root_nodes:
        print_branch(
            mapper=mapper,
            node=root_node,
            nodes=persisted_nodes,
        )


if __name__ == "__main__":
    main()
