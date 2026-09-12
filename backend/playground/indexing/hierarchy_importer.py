import json
from pathlib import Path
from uuid import uuid4

from app.database.database import Database
from app.indexing.hierarchy_importer import HierarchyImporter
from app.repositories.document_node_repository import (
    DocumentNodeRepository
)

JSON_FILE = Path(
    r"C:\Users\elect\Documents\PRANOVA\intellidocs\documents\profiles\56. P.U. (A) 2022_140 Perintah Gaji Minimum 2022.json"
)

TEST_DOCUMENT_ID = "40cbd327-0728-4803-b0a4-be7e85e52b8d"


def main():

    print("Loading hierarchy JSON...")

    with open(
        JSON_FILE,
        "r",
        encoding="utf-8"
    ) as f:

        hierarchy = json.load(f)

    db = Database()

    importer = HierarchyImporter(db)

    repository = DocumentNodeRepository(db)

    print(
        f"Importing hierarchy for document: "
        f"{TEST_DOCUMENT_ID}"
    )

    repository.delete_by_document(TEST_DOCUMENT_ID)

    importer.import_hierarchy(
        document_id=TEST_DOCUMENT_ID,
        hierarchy=hierarchy
    )

    nodes = repository.get_by_document(
        TEST_DOCUMENT_ID
    )

    print(
        f"\nImported {len(nodes)} node(s)\n"
    )

    for node in nodes:

        print(
            f"{node.node_type:<15} "
            f"{node.identifier:<20} "
            f"parent={node.parent_id}"
        )


if __name__ == "__main__":
    main()
