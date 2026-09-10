from typing import List

from app.models.document_node import DocumentNode


class DocumentNodeRepository:

    def __init__(self, db):
        self.db = db


    def create(self,node: DocumentNode
    ) -> None:

        query = """
        INSERT INTO document_nodes (
            id,
            document_id,
            parent_id,
            node_type,
            identifier,
            title,
            sequence_no,
            depth,
            start_page,
            start_character,
            end_page
        )
        VALUES (
            %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
        )
        """

        self.db.execute(
            query,
            (
                node.id,
                node.document_id,
                node.parent_id,
                node.node_type,
                node.identifier,
                node.title,
                node.sequence_no,
                node.depth,
                node.start_page,
                node.start_character,
                node.end_page,
            ),
        )


    def bulk_create(self,nodes: List[DocumentNode]
    ) -> None:

        query = """
        INSERT INTO document_nodes (
            id,
            document_id,
            parent_id,
            node_type,
            identifier,
            title,
            sequence_no,
            depth,
            start_page,
            start_character,
            end_page
        )
        VALUES (
            %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
        )
        """

        values = [
            (
                n.id,
                n.document_id,
                n.parent_id,
                n.node_type,
                n.identifier,
                n.title,
                n.sequence_no,
                n.depth,
                n.start_page,
                n.start_character,
                n.end_page,
            )
            for n in nodes
        ]

        self.db.executemany(
            query,
            values
        )


    def get_by_id(self,node_id: str):

        # Select columns explicitly so repository mapping does not depend on
        # the physical column order inside PostgreSQL.
        query = """
        SELECT
            id,
            document_id,
            parent_id,
            node_type,
            identifier,
            title,
            sequence_no,
            depth,
            start_page,
            start_character,
            end_page
        FROM document_nodes
        WHERE id = %s
        """

        return self.db.fetch_one(
            query,
            (node_id,)
        )


    def get_by_document(
        self,
        document_id: str
    ) -> list[DocumentNode]:

        # Keep the selected column order aligned with the DocumentNode model.
        query = """
        SELECT
            id,
            document_id,
            parent_id,
            node_type,
            identifier,
            title,
            sequence_no,
            depth,
            start_page,
            start_character,
            end_page
        FROM document_nodes
        WHERE document_id = %s
        ORDER BY depth, sequence_no
        """

        rows = self.db.fetch_all(
            query,
            (document_id,)
        )

        nodes = []

        for row in rows:

            nodes.append(
                DocumentNode(
                    id=row[0],
                    document_id=row[1],
                    parent_id=row[2],
                    node_type=row[3],
                    identifier=row[4],
                    title=row[5],
                    sequence_no=row[6],
                    depth=row[7],
                    start_page=row[8],
                    start_character=row[9],
                    end_page=row[10]
                )
            )

        return nodes


    def get_children(self,parent_id: str):

        query = """
        SELECT *
        FROM document_nodes
        WHERE parent_id = %s
        ORDER BY sequence_no
        """

        return self.db.fetch_all(query,(parent_id,))


    def update(self,node: DocumentNode
    ) -> None:

        query = """
        UPDATE document_nodes
        SET
            parent_id = %s,
            node_type = %s,
            identifier = %s,
            title = %s,
            sequence_no = %s,
            depth = %s,
            start_page = %s,
            start_character = %s,
            end_page = %s
        WHERE id = %s
        """

        self.db.execute(
            query,
            (
                node.parent_id,
                node.node_type,
                node.identifier,
                node.title,
                node.sequence_no,
                node.depth,
                node.start_page,
                node.start_character,
                node.end_page,
                node.id,
            ),
        )


    def delete(
        self,
        node_id: str
    ) -> None:

        query = """
        DELETE FROM document_nodes
        WHERE id = %s
        """

        self.db.execute(query,(node_id,))


    def delete_by_document(
        self,
        document_id: str
    ) -> None:

        query = """
        DELETE FROM document_nodes
        WHERE document_id = %s
        """
        self.db.execute(query,(document_id,))


    def update_page_range(
        self,
        node_id: str,
        start_page: int | None,
        start_character: int | None,
        end_page: int | None
    ) -> None:

        query = """
        UPDATE document_nodes
        SET
            start_page = %s,
            start_character = %s,
            end_page = %s
        WHERE id = %s
        """

        self.db.execute(
            query,
            (
                start_page,
                start_character,
                end_page,
                node_id
            )
        )


    def bulk_update_page_ranges(
        self,
        nodes: list[DocumentNode]
    ) -> None:

        query = """
        UPDATE document_nodes
        SET
            start_page = %s,
            start_character = %s,
            end_page = %s
        WHERE id = %s
        """

        for node in nodes:

            self.db.execute(
                query,
                (
                    node.start_page,
                    node.start_character,
                    node.end_page,
                    node.id
                )
            )
