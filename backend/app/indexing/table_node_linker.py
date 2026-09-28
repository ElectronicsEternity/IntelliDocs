# ========================================
# File: table_node_linker.py
# ========================================
#
# Purpose
# -------
# Link normalized tables to hierarchy TABLE nodes.
#
# Responsibilities
# ----------------
# - Match tables by their mapped page boundaries.
# - Reject missing or ambiguous table-node matches.
# - Return node IDs in logical-table order.
#
# ========================================

from app.models.document_node import DocumentNode
from collections import defaultdict
from uuid import NAMESPACE_URL, uuid5


# ==========================================================
# Table Node Linker
# ==========================================================

class TableNodeLinker:

    TABLE_OWNER_TYPES = {"SCHEDULE", "HEADING"}

    @staticmethod
    def _standalone_parent(
        nodes: list[DocumentNode],
        start_page: int,
        end_page: int,
    ) -> DocumentNode:
        candidates = [
            node
            for node in nodes
            if (
                node.node_type.upper() != "TABLE"
                and node.start_page is not None
                and node.end_page is not None
                and node.start_page <= start_page
                and node.end_page >= end_page
            )
        ]
        if not candidates:
            raise ValueError(
                f"Standalone table on pages {start_page}-{end_page} "
                "has no containing hierarchy node."
            )
        best_depth = max(node.depth for node in candidates)
        deepest = [node for node in candidates if node.depth == best_depth]
        smallest_span = min(
            node.end_page - node.start_page for node in deepest
        )
        closest = [
            node
            for node in deepest
            if node.end_page - node.start_page == smallest_span
        ]
        if len(closest) != 1:
            raise ValueError(
                f"Standalone table on pages {start_page}-{end_page} "
                f"has {len(closest)} equally specific hierarchy parents."
            )
        return closest[0]

    @staticmethod
    def _resequence_children(
        nodes: list[DocumentNode],
        parent_id: str,
    ) -> None:
        siblings = [node for node in nodes if node.parent_id == parent_id]
        siblings.sort(key=lambda node: (
            node.start_page is None,
            node.start_page if node.start_page is not None else 10**9,
            node.start_character is None,
            node.start_character if node.start_character is not None else 10**9,
            node.sequence_no,
            node.id,
        ))
        for sequence_no, node in enumerate(siblings):
            node.sequence_no = sequence_no

    def _create_standalone_node(
        self,
        *,
        table: dict,
        table_number: int,
        start_page: int,
        end_page: int,
        nodes: list[DocumentNode],
    ) -> DocumentNode:
        parent = self._standalone_parent(nodes, start_page, end_page)
        table_id = str(table.get("table_id") or f"table-{table_number}")
        node_id = str(uuid5(
            NAMESPACE_URL,
            f"intellidocs:{parent.document_id}:{table_id}:{start_page}:{end_page}",
        ))
        existing = next((node for node in nodes if node.id == node_id), None)
        if existing is not None:
            return existing
        node = DocumentNode(
            id=node_id,
            document_id=parent.document_id,
            parent_id=parent.id,
            node_type="TABLE",
            identifier=table_id,
            title=str(table.get("title") or f"Standalone table {table_number}"),
            sequence_no=0,
            depth=parent.depth + 1,
            start_page=start_page,
            start_character=None,
            end_page=end_page,
        )
        nodes.append(node)
        self._resequence_children(nodes, parent.id)
        return node

    @staticmethod
    def _document_order(nodes: list[DocumentNode]) -> list[DocumentNode]:
        """Return TABLE nodes in hierarchy DFS order, not SQL depth order."""
        children = defaultdict(list)
        lookup = {node.id: node for node in nodes}
        for node in nodes:
            children[node.parent_id].append(node)
        for siblings in children.values():
            siblings.sort(key=lambda node: node.sequence_no)

        ordered = []

        def visit(node):
            if node.node_type.upper() == "TABLE":
                ordered.append(node)
            for child in children[node.id]:
                visit(child)

        for root in children[None]:
            visit(root)
        if len(ordered) != sum(
            node.node_type.upper() == "TABLE" for node in lookup.values()
        ):
            raise ValueError("Table hierarchy is cyclic or disconnected.")
        return ordered

    # Match every normalized table to exactly one TABLE node.
    def link_tables(
        self,
        normalized_tables: list[dict],
        nodes: list[DocumentNode],
    ) -> list[str]:

        # Keep only hierarchy nodes representing tables.
        table_nodes = self._document_order(nodes)
        structural_owners = [
            node
            for node in nodes
            if node.node_type.upper() in self.TABLE_OWNER_TYPES
        ]

        # When several tables begin on one page, both model passes must report
        # the same count. Only then may document order break the tie safely.
        tables_by_page = defaultdict(list)
        nodes_by_page = defaultdict(list)
        for index, table in enumerate(normalized_tables):
            pages = table.get("page_numbers", [])
            if pages:
                tables_by_page[min(pages)].append(index)
        for node in table_nodes:
            if node.start_page is not None:
                nodes_by_page[node.start_page].append(node)
        page_fallback = {}
        for page, table_indexes in tables_by_page.items():
            candidates = nodes_by_page.get(page, [])
            if len(candidates) == len(table_indexes):
                page_fallback.update(zip(table_indexes, candidates))

        # Prevent one node from owning multiple logical tables.
        used_node_ids = set()
        linked_node_ids = []

        # Preserve the normalized logical-table order.
        for table_index, table in enumerate(normalized_tables):
            table_number = table_index + 1
            page_numbers = table.get("page_numbers", [])

            # A table must retain at least one source page.
            if not page_numbers:
                raise ValueError(
                    f"Table {table_number} has no pages."
                )

            start_page = min(page_numbers)
            end_page = max(page_numbers)

            # Match the exact range produced by PageMapper.
            candidates = [
                node
                for node in table_nodes
                if (
                    node.start_page == start_page
                    and node.end_page == end_page
                    and node.id not in used_node_ids
                )
            ]
            same_start_candidates = [
                node
                for node in table_nodes
                if (
                    node.start_page == start_page
                    and node.id not in used_node_ids
                )
            ]

            if len(candidates) == 1:
                matched_node = candidates[0]
            else:
                # The hierarchy pass provides start pages; the separate table
                # pass provides complete ranges. Reconcile them only when the
                # number and order of same-page tables agree exactly.
                fallback = page_fallback.get(table_index)
                matched_node = (
                    fallback
                    if fallback is not None and fallback.id not in used_node_ids
                    else None
                )

            # Some legal schedules and amendment lists are physically tables
            # but correctly remain SCHEDULE/HEADING nodes in the hierarchy.
            # An exact, unique page-range owner is strong enough to link without
            # inventing a duplicate TABLE node.
            structural_candidates = []
            if matched_node is None:
                structural_candidates = [
                    node
                    for node in structural_owners
                    if (
                        node.start_page == start_page
                        and node.end_page == end_page
                        and node.id not in used_node_ids
                    )
                ]
                if len(structural_candidates) == 1:
                    matched_node = structural_candidates[0]

            # A valid physical table may live in front matter or another
            # location omitted from the semantic hierarchy. Create a local,
            # deterministic TABLE child only when no existing candidate is
            # ambiguous.
            if (
                matched_node is None
                and not candidates
                and not same_start_candidates
                and not structural_candidates
            ):
                matched_node = self._create_standalone_node(
                    table=table,
                    table_number=table_number,
                    start_page=start_page,
                    end_page=end_page,
                    nodes=nodes,
                )

            # Reject guesses that could select a wrong branch.
            if matched_node is None:
                raise ValueError(
                    f"Table {table_number} on pages "
                    f"{start_page}-{end_page} matched "
                    f"{len(candidates)} TABLE nodes and "
                    f"{len(structural_candidates)} "
                    "structural table owners."
                )

            # The visual table pass owns the complete physical range.
            matched_node.start_page = start_page
            matched_node.end_page = end_page
            used_node_ids.add(matched_node.id)
            linked_node_ids.append(matched_node.id)

        # Return one verified node ID for every table.
        return linked_node_ids
