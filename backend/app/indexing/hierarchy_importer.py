from uuid import uuid4

from app.indexing.document_profile_validator import (
    DocumentProfileValidationError,
    DocumentProfileValidator,
)
from app.models.document_node import DocumentNode
from app.repositories.document_node_repository import (
    DocumentNodeRepository
)


class HierarchyImporter:

    # Prepare node conversion, validation, and persistence.
    def __init__(self,db):

        # Retain the database wrapper for this importer.
        self.db = db

        # Use the repository only at the final write boundary.
        self.repository = DocumentNodeRepository(db)

        # Defensively validate profiles before conversion.
        self.validator = DocumentProfileValidator()


    # Validate, convert, and persist one hierarchy.
    def import_hierarchy(
        self,
        document_id: str,
        hierarchy: dict
    ) -> None:

        # Build and validate nodes before reaching the
        # database boundary.
        nodes = self.build_nodes(
            document_id=document_id,
            hierarchy=hierarchy,
        )

        # Persist only a completely validated node collection.
        self.repository.bulk_create(nodes)


    # Build hierarchy nodes without writing to PostgreSQL.
    def build_nodes(
        self,
        document_id: str,
        hierarchy: dict,
    ) -> list[DocumentNode]:

        # Refuse invalid raw profiles before database writes.
        result = self.validator.validate(hierarchy)

        # Stop before node creation when validation fails.
        if not result.is_valid:
            raise DocumentProfileValidationError(
                result.errors
            )

        # Collect every converted node in memory first.
        nodes = []

        # Begin recursive conversion from the DOCUMENT root.
        self._process_node(
            document_id=document_id,
            node=hierarchy,
            parent_id=None,
            depth=0,
            sequence_no=0,
            nodes=nodes
        )

        # Return in-memory nodes for validation or persistence.
        return nodes


    # Convert one JSON node and then all of its children.
    def _process_node(
        self,
        document_id: str,
        node: dict,
        parent_id: str | None,
        depth: int,
        sequence_no: int,
        nodes: list
    ) -> str:

        # Give this database node its own unique identifier.
        node_id = str(uuid4())

        # Convert raw JSON fields into a DocumentNode model.
        document_node = DocumentNode(
            id=node_id,
            document_id=document_id,
            parent_id=parent_id,
            node_type=node.get("type",""),
            identifier=node.get("identifier",""),
            title=node.get("title",""),
            sequence_no=sequence_no,
            depth=depth,
            start_page=None,
            end_page=None
        )

        # Store node for later bulk insert.
        nodes.append(document_node)

        # Get child nodes.
        children = node.get("children",[])

        # Recursively process each child.
        #
        # Example:
        #
        # DOCUMENT
        # └── PART I
        #     └── SECTION 2
        #         └── SUBSECTION (1)
        #
        # Each child receives:
        # - current node_id as parent_id
        # - depth + 1
        # - its position among siblings
        for index,child in enumerate(children):

            self._process_node(
                document_id=document_id,
                node=child,
                parent_id=node_id,
                depth=depth + 1,
                sequence_no=index,
                nodes=nodes
            )

        # Return generated node id so it can be used
        # as parent_id by descendant nodes.
        return node_id
