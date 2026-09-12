import os
from pathlib import Path

from app.database.database import Database
from app.indexing.node_scope_extractor import NodeScopeExtractor
from app.ingestion.parser import PDFParser
from app.repositories.document_node_repository import DocumentNodeRepository


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

    # Load the real hierarchy from PostgreSQL.
    nodes = repository.get_by_document(TEST_DOCUMENT_ID)

    if not nodes:
        print("No DocumentNode records found.")
        return

    # Read the real PDF and extract every title-or-identifier node scope.
    document = PDFParser(PDF_FILE).extract_text(owner_id=os.environ["INTELLIDOCS_DEV_USER_ID"])

    print(f"Document ID: {TEST_DOCUMENT_ID}")
    print(f"PDF: {PDF_FILE.name}")
    print("\n=== Complete Node Scopes Started ===")

    scopes = extractor.extract_node_scopes(document=document, nodes=nodes)

    for index, scope in enumerate(scopes):
        # The following mapped anchor supplies the current scope's end boundary.
        next_anchor = scopes[index + 1]["anchor_text"] if index < len(scopes) - 1 else "DOCUMENT END"

        print("\n" + "=" * 100)
        print(
            f"Scope {index + 1}/{len(scopes)} | {scope['node_type']} | "
            f"depth={scope['depth']} | sequence={scope['sequence_no']}"
        )
        print(f"Title: {scope['title'] or '[no title]'}")
        print(f"Identifier: {scope['identifier'] or '[no identifier]'}")
        print(f"Anchor: {scope['anchor_text']}")
        print(
            f"Boundary: {scope['start_page']}:{scope['start_character']} "
            f"to {scope['end_page']}:{scope['end_character']}"
        )
        print(f"Next anchor: {next_anchor}")
        print("-" * 100)
        print(scope["text"])

    print("\n=== Complete Node Scopes Ended ===")

    print("\nResults:")
    print(f"Scopes printed: {len(scopes)}")


if __name__ == "__main__":
    main()
