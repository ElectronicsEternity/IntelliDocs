from app.models.document import Document
from app.models.document_node import DocumentNode


class NodeScopeExtractor:

    # Build readable labels from the root to one node.
    def _build_hierarchy_path(
        self,
        node: DocumentNode,
        nodes_by_id: dict[str, DocumentNode],
    ) -> tuple[str, ...]:

        # Collect labels while walking from child to parent.
        labels = []
        current_node: DocumentNode | None = node

        # Stop after reaching the root of this hierarchy.
        while current_node is not None:
            label = (
                (current_node.title or "").strip()
                or (current_node.identifier or "").strip()
            )

            # Omit structural nodes without readable labels.
            if label:
                labels.append(label)

            # A missing parent marks the hierarchy root.
            if current_node.parent_id is None:
                break

            current_node = nodes_by_id.get(
                current_node.parent_id
            )

        # Reverse child-first labels into root-first order.
        return tuple(reversed(labels))

    def extract_node_scopes(
        self,
        document: Document,
        nodes: list[DocumentNode],
    ) -> list[dict]:
        """Extract non-overlapping mapped-node text."""

        # Index every node for fast parent traversal.
        nodes_by_id = {node.id: node for node in nodes}

        # Tables are chunked from geometry, not page text.
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

        # Keep anchors with complete physical positions.
        mapped_anchored_nodes = [
            node
            for node in anchored_nodes
            if (
                node.start_page is not None
                and node.start_character is not None
            )
        ]

        # Reject gaps that could merge unrelated scopes.
        if len(mapped_anchored_nodes) != len(anchored_nodes):
            missing_count = (
                len(anchored_nodes)
                - len(mapped_anchored_nodes)
            )
            raise ValueError(
                f"Cannot extract node scopes: {missing_count} "
                "anchored node(s) have no complete "
                "start position."
            )

        # Physical order uses page and character position.
        # Hierarchy depth remains descriptive metadata;
        # it does not determine where text physically appears.
        ordered_nodes = sorted(
            mapped_anchored_nodes,
            key=lambda node: (
                node.start_page,
                node.start_character,
            ),
        )

        pages_by_number = {
            page.page_number: page
            for page in document.pages
        }

        if not document.pages:
            return []

        last_page = max(
            document.pages,
            key=lambda page: page.page_number,
        )

        scopes = []

        for index, node in enumerate(ordered_nodes):
            # Repeat this check to narrow optional fields.
            if (
                node.start_page is None
                or node.start_character is None
            ):
                raise ValueError(
                    f"Node {node.id} has no complete "
                    "start position."
                )

            start_page = node.start_page
            start_character = node.start_character

            # The next anchor marks this scope's exclusive end.
            # The final anchor ends at the document end.
            if index < len(ordered_nodes) - 1:
                next_node = ordered_nodes[index + 1]

                if (
                    next_node.start_page is None
                    or next_node.start_character is None
                ):
                    raise ValueError(
                        f"Node {next_node.id} has no complete "
                        f"start position."
                    )

                end_page = next_node.start_page
                end_character = next_node.start_character
            else:
                end_page = last_page.page_number
                end_character = len(last_page.text)

            start_position = (
                start_page,
                start_character,
            )
            end_position = (
                end_page,
                end_character,
            )

            if end_position <= start_position:
                raise ValueError(
                    "Invalid scope boundary for node "
                    f"{node.id}: "
                    f"{start_position} to {end_position}."
                )

            scope_text = self._extract_text_between(
                pages_by_number=pages_by_number,
                start_page=start_page,
                start_character=start_character,
                end_page=end_page,
                end_character=end_character,
            )

            # Prefer the title, then use the identifier.
            anchor_text = (
                node.title.strip()
                if node.title and node.title.strip()
                else (node.identifier or "").strip()
            )

            # Keep every scope value explicitly named.
            scopes.append(
                {
                    "node_id": node.id,
                    "document_id": node.document_id,
                    "parent_id": node.parent_id,
                    "node_type": node.node_type,
                    "identifier": node.identifier,
                    "title": node.title,
                    "anchor_text": anchor_text,
                    "hierarchy_path": (
                        self._build_hierarchy_path(
                            node,
                            nodes_by_id,
                        )
                    ),
                    "depth": node.depth,
                    "sequence_no": node.sequence_no,
                    "start_page": start_page,
                    "start_character": start_character,
                    "end_page": end_page,
                    "end_character": end_character,
                    "text": scope_text,
                }
            )

        return scopes

    def _extract_text_between(
        self,
        pages_by_number: dict,
        start_page: int,
        start_character: int,
        end_page: int,
        end_character: int,
    ) -> str:
        """Extract text between two physical positions."""

        if start_page not in pages_by_number:
            raise ValueError(
                f"Start page {start_page} was not found."
            )

        if end_page not in pages_by_number:
            raise ValueError(
                f"End page {end_page} was not found."
            )

        start_page_text = pages_by_number[start_page].text
        end_page_text = pages_by_number[end_page].text

        if not 0 <= start_character <= len(start_page_text):
            raise ValueError(
                "Start character "
                f"{start_character} is outside "
                f"page {start_page}."
            )

        if not 0 <= end_character <= len(end_page_text):
            raise ValueError(
                f"End character {end_character} is outside "
                f"page {end_page}."
            )

        # Slice directly when both boundaries share a page.
        # The end character remains exclusive.
        if start_page == end_page:
            return start_page_text[
                start_character:end_character
            ]

        text_parts = [start_page_text[start_character:]]

        # Include pages between both boundary pages.
        for page_number in range(start_page + 1, end_page):

            if page_number not in pages_by_number:
                raise ValueError(
                    f"Page {page_number} was not found."
                )

            middle_page = pages_by_number[page_number]
            text_parts.append(middle_page.text)

        # Stop before the next anchor on the final page.
        text_parts.append(end_page_text[:end_character])

        return "\n".join(text_parts)
