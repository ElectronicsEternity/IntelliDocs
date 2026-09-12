import os
from pathlib import Path

from app.database.database import Database
from app.indexing.node_scope_extractor import NodeScopeExtractor
from app.indexing.node_scope_validator import (
    NodeScopeValidator,
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


def main():
    db = Database()
    repository = DocumentNodeRepository(db)
    extractor = NodeScopeExtractor()
    validator = NodeScopeValidator()

    # Load the real mapped hierarchy from PostgreSQL.
    nodes = repository.get_by_document(TEST_DOCUMENT_ID)

    if not nodes:
        print("No DocumentNode records found.")
        return

    # Remember all persisted positions so this playground can prove that
    # scope extraction performs no database updates.
    database_values_before = {
        node.id: (
            node.start_page,
            node.start_character,
            node.end_page,
        )
        for node in nodes
    }

    parser = PDFParser(PDF_FILE)
    document = parser.extract_text(owner_id=os.environ["INTELLIDOCS_DEV_USER_ID"])

    print(f"Document ID: {TEST_DOCUMENT_ID}")
    print(f"PDF: {PDF_FILE.name}")
    print(f"Nodes loaded: {len(nodes)}")
    print(f"PDF pages loaded: {document.total_pages}")
    print("\n=== NodeScopeExtractor Started ===")

    scopes = extractor.extract_node_scopes(
        document=document,
        nodes=nodes,
    )

    print("=== NodeScopeExtractor Ended ===\n")

    # Count every node that can be anchored by title or identifier text.
    anchored_nodes = [
        node
        for node in nodes
        if (
            node.node_type.upper() != "TABLE"
            and (
                (node.title and node.title.strip())
                or (
                    node.identifier
                    and node.identifier.strip()
                )
            )
        )
    ]

    result = validator.validate(scopes)

    # Check every extracted scope and prepare readable terminal output.
    for index, scope in enumerate(scopes):

        # Show the title when available and otherwise show the identifier.
        display_title = scope["title"] or scope["identifier"]

        # Limit long titles to the first 80 characters in the terminal.
        if len(display_title) > 80:
            display_title = f"{display_title[:80]}..."

        # Convert extracted scope text into a readable one-line preview.
        text_preview = " ".join(scope["text"].split())

        # Limit long previews to the first 100 characters in the terminal.
        if len(text_preview) > 100:
            text_preview = f"{text_preview[:100]}..."

        print(
            f"Scope {index + 1} | "
            f"{scope['node_type']} | "
            f"depth={scope['depth']} | "
            f"sequence={scope['sequence_no']} | "
            f"identifier={scope['identifier'] or '-'} | "
            f"start={scope['start_page']}:"
            f"{scope['start_character']} | "
            f"end={scope['end_page']}:"
            f"{scope['end_character']} | "
            f"characters={len(scope['text'])} | "
            f"anchor={display_title}"
        )
        print(f"  Preview: {text_preview}")

    # Reload fresh objects and compare their persisted values with the
    # snapshot taken before extraction.
    nodes_after_test = repository.get_by_document(TEST_DOCUMENT_ID)

    database_values_after = {
        node.id: (
            node.start_page,
            node.start_character,
            node.end_page,
        )
        for node in nodes_after_test
    }

    database_unchanged = (
        database_values_after == database_values_before
    )

    print("\nResults:")
    print(f"Anchored nodes: {len(anchored_nodes)}")
    print(f"Scopes extracted: {len(scopes)}")
    print(f"Empty scopes: {len(result.empty_scopes)}")
    print(
        "Anchor mismatches: "
        f"{len(result.anchor_mismatches)}"
    )
    print(
        "Boundary violations: "
        f"{len(result.boundary_violations)}"
    )
    print(f"Scopes valid: {result.is_valid}")
    print(f"Database unchanged: {database_unchanged}")


if __name__ == "__main__":
    main()
