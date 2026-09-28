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


# ==========================================================
# Table Node Linker
# ==========================================================

class TableNodeLinker:

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

            # Reject guesses that could select a wrong branch.
            if matched_node is None:
                raise ValueError(
                    f"Table {table_number} on pages "
                    f"{start_page}-{end_page} matched "
                    f"{len(candidates)} TABLE nodes."
                )

            # The visual table pass owns the complete physical range.
            matched_node.start_page = start_page
            matched_node.end_page = end_page
            used_node_ids.add(matched_node.id)
            linked_node_ids.append(matched_node.id)

        # Return one verified node ID for every table.
        return linked_node_ids
