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


# ==========================================================
# Table Node Linker
# ==========================================================

class TableNodeLinker:

    # Match every normalized table to exactly one TABLE node.
    def link_tables(
        self,
        normalized_tables: list[dict],
        nodes: list[DocumentNode],
    ) -> list[str]:

        # Keep only hierarchy nodes representing tables.
        table_nodes = [
            node
            for node in nodes
            if node.node_type.upper() == "TABLE"
        ]

        # Prevent one node from owning multiple logical tables.
        used_node_ids = set()
        linked_node_ids = []

        # Preserve the normalized logical-table order.
        for table_number, table in enumerate(
            normalized_tables,
            start=1,
        ):
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

            # Reject guesses that could select a wrong branch.
            if len(candidates) != 1:
                raise ValueError(
                    f"Table {table_number} on pages "
                    f"{start_page}-{end_page} matched "
                    f"{len(candidates)} TABLE nodes."
                )

            matched_node = candidates[0]
            used_node_ids.add(matched_node.id)
            linked_node_ids.append(matched_node.id)

        # Return one verified node ID for every table.
        return linked_node_ids
