# ========================================
# File: hierarchy_validator.py
# ========================================
#
# Purpose
# -------
# Validate an imported DocumentNode hierarchy.
#
# Responsibilities
# ----------------
# - Verify node lookup completeness.
# - Verify parent and child relationships.
# - Verify depth and sibling sequence values.
#
# ========================================

from dataclasses import dataclass

from app.models.document_node import DocumentNode


# ==========================================================
# Validation Result
# ==========================================================

@dataclass(frozen=True)
class HierarchyValidationResult:
    every_node_indexed: bool
    hierarchy_preserved: bool
    sibling_order_preserved: bool
    missing_parent_nodes: tuple[DocumentNode, ...]
    depth_violations: tuple[DocumentNode, ...]
    duplicate_sequence_nodes: tuple[DocumentNode, ...]

    @property
    def is_valid(self) -> bool:
        return (
            self.every_node_indexed
            and self.hierarchy_preserved
            and self.sibling_order_preserved
            and not self.missing_parent_nodes
            and not self.depth_violations
            and not self.duplicate_sequence_nodes
        )


# ==========================================================
# Hierarchy Validator
# ==========================================================

class HierarchyValidator:

    # Validate hierarchy outputs built by PageMapper.
    def validate(
        self,
        nodes: list[DocumentNode],
        node_lookup: dict[str, DocumentNode],
        children_by_parent: dict[
            str,
            list[DocumentNode],
        ],
    ) -> HierarchyValidationResult:
        every_node_indexed = all(
            node_lookup.get(node.id) is node
            for node in nodes
        )

        returned_children = []

        for children in children_by_parent.values():
            returned_children.extend(children)

        expected_child_ids = {
            node.id
            for node in nodes
            if node.parent_id is not None
        }
        returned_child_ids = {
            node.id for node in returned_children
        }
        hierarchy_preserved = (
            returned_child_ids == expected_child_ids
            and len(returned_children)
            == len(expected_child_ids)
        )
        sibling_order_preserved = all(
            children == sorted(
                children,
                key=lambda child: child.sequence_no,
            )
            for children in children_by_parent.values()
        )

        missing_parent_nodes = self._find_missing_parents(
            nodes,
            node_lookup,
        )
        depth_violations = self._find_depth_violations(
            nodes,
            node_lookup,
        )
        duplicate_sequence_nodes = (
            self._find_duplicate_sequences(nodes)
        )

        return HierarchyValidationResult(
            every_node_indexed=every_node_indexed,
            hierarchy_preserved=hierarchy_preserved,
            sibling_order_preserved=(
                sibling_order_preserved
            ),
            missing_parent_nodes=tuple(
                missing_parent_nodes
            ),
            depth_violations=tuple(depth_violations),
            duplicate_sequence_nodes=tuple(
                duplicate_sequence_nodes
            ),
        )

    # Find nodes whose parent is absent from the lookup.
    def _find_missing_parents(
        self,
        nodes: list[DocumentNode],
        node_lookup: dict[str, DocumentNode],
    ) -> list[DocumentNode]:
        return [
            node
            for node in nodes
            if (
                node.parent_id is not None
                and node.parent_id not in node_lookup
            )
        ]

    # Find children whose depth does not follow the parent.
    def _find_depth_violations(
        self,
        nodes: list[DocumentNode],
        node_lookup: dict[str, DocumentNode],
    ) -> list[DocumentNode]:
        violations = []

        for node in nodes:
            if node.parent_id is None:
                continue

            parent = node_lookup.get(node.parent_id)

            if parent is None:
                continue

            if node.depth != parent.depth + 1:
                violations.append(node)

        return violations

    # Find siblings that reuse the same sequence number.
    def _find_duplicate_sequences(
        self,
        nodes: list[DocumentNode],
    ) -> list[DocumentNode]:
        seen = set()
        duplicates = []

        for node in nodes:
            key = (node.parent_id, node.sequence_no)

            if key in seen:
                duplicates.append(node)
                continue

            seen.add(key)

        return duplicates
