# ========================================
# File: page_mapping_validator.py
# ========================================
#
# Purpose
# -------
# Validate mapped node positions and page ranges.
#
# Responsibilities
# ----------------
# - Verify searchable node anchors.
# - Verify physical hierarchy order.
# - Verify parent and child page ranges.
# - Verify TABLE nodes use geometric anchors.
#
# ========================================

from dataclasses import dataclass

from app.models.document import Document
from app.models.document_node import DocumentNode


# ==========================================================
# Validation Result
# ==========================================================

@dataclass(frozen=True)
class PageMappingValidationResult:
    missing_anchor_nodes: tuple[DocumentNode, ...]
    anchor_text_mismatches: tuple[DocumentNode, ...]
    order_violations: tuple[DocumentNode, ...]
    incomplete_range_nodes: tuple[DocumentNode, ...]
    invalid_range_nodes: tuple[DocumentNode, ...]
    parent_range_violations: tuple[DocumentNode, ...]
    parent_position_violations: tuple[DocumentNode, ...]
    table_character_violations: tuple[DocumentNode, ...]
    unanchored_character_nodes: tuple[DocumentNode, ...]

    @property
    def is_valid(self) -> bool:
        return not any(
            (
                self.missing_anchor_nodes,
                self.anchor_text_mismatches,
                self.order_violations,
                self.incomplete_range_nodes,
                self.invalid_range_nodes,
                self.parent_range_violations,
                self.parent_position_violations,
                self.table_character_violations,
                self.unanchored_character_nodes,
            )
        )


# ==========================================================
# Page Mapping Validator
# ==========================================================

class PageMappingValidator:

    # Validate a complete PageMapper result.
    def validate(
        self,
        document: Document,
        nodes: list[DocumentNode],
    ) -> PageMappingValidationResult:
        node_lookup = {
            node.id: node for node in nodes
        }
        missing_anchor_nodes = [
            node
            for node in nodes
            if (
                self._requires_text_anchor(node)
                and (
                    node.start_page is None
                    or node.start_character is None
                )
            )
        ]
        anchor_text_mismatches = (
            self._find_anchor_text_mismatches(
                document,
                nodes,
            )
        )
        order_violations = (
            self.find_physical_order_violations(nodes)
        )
        incomplete_range_nodes = [
            node
            for node in nodes
            if (
                node.start_page is None
                or node.end_page is None
            )
        ]
        invalid_range_nodes = [
            node
            for node in nodes
            if (
                node.start_page is not None
                and node.end_page is not None
                and node.end_page < node.start_page
            )
        ]
        parent_range_violations = (
            self._find_parent_range_violations(
                nodes,
                node_lookup,
            )
        )
        parent_position_violations = (
            self._find_parent_position_violations(
                document,
                nodes,
                node_lookup,
            )
        )
        table_character_violations = [
            node
            for node in nodes
            if (
                node.node_type.upper() == "TABLE"
                and node.start_character is not None
            )
        ]
        unanchored_character_nodes = [
            node
            for node in nodes
            if (
                not self._has_text_anchor(node)
                and node.node_type.upper() != "TABLE"
                and node.start_character is not None
            )
        ]

        return PageMappingValidationResult(
            missing_anchor_nodes=tuple(
                missing_anchor_nodes
            ),
            anchor_text_mismatches=tuple(
                anchor_text_mismatches
            ),
            order_violations=tuple(order_violations),
            incomplete_range_nodes=tuple(
                incomplete_range_nodes
            ),
            invalid_range_nodes=tuple(
                invalid_range_nodes
            ),
            parent_range_violations=tuple(
                parent_range_violations
            ),
            parent_position_violations=tuple(
                parent_position_violations
            ),
            table_character_violations=tuple(
                table_character_violations
            ),
            unanchored_character_nodes=tuple(
                unanchored_character_nodes
            ),
        )

    # Find mapped nodes that move backwards in DFS order.
    def find_physical_order_violations(
        self,
        nodes: list[DocumentNode],
    ) -> list[DocumentNode]:
        children_by_parent = {}

        for node in nodes:
            children_by_parent.setdefault(
                node.parent_id,
                [],
            ).append(node)

        for children in children_by_parent.values():
            children.sort(
                key=lambda child: child.sequence_no
            )

        violations = []
        previous_position = None

        def inspect_branch(node: DocumentNode) -> None:
            nonlocal previous_position

            if (
                node.start_page is not None
                and node.start_character is not None
            ):
                current_position = (
                    node.start_page,
                    node.start_character,
                )

                if (
                    previous_position is not None
                    and current_position
                    < previous_position
                ):
                    violations.append(node)

                previous_position = current_position

            for child in children_by_parent.get(
                node.id,
                [],
            ):
                inspect_branch(child)

        for root in children_by_parent.get(None, []):
            inspect_branch(root)

        return violations

    # Decide whether a node owns searchable text.
    def _requires_text_anchor(
        self,
        node: DocumentNode,
    ) -> bool:
        return (
            node.node_type.upper() != "TABLE"
            and self._has_text_anchor(node)
        )

    # Check whether a title or identifier is available.
    def _has_text_anchor(
        self,
        node: DocumentNode,
    ) -> bool:
        return bool(
            (node.title or "").strip()
            or (node.identifier or "").strip()
        )

    # Find positions that do not point to their anchor text.
    def _find_anchor_text_mismatches(
        self,
        document: Document,
        nodes: list[DocumentNode],
    ) -> list[DocumentNode]:
        pages = {
            page.page_number: page
            for page in document.pages
        }
        mismatches = []

        for node in nodes:
            if not self._requires_text_anchor(node):
                continue

            if (
                node.start_page is None
                or node.start_character is None
            ):
                continue

            page = pages.get(node.start_page)

            if page is None:
                mismatches.append(node)
                continue

            anchor = (
                (node.title or "").strip()
                or (node.identifier or "").strip()
            )
            page_text = page.text[node.start_character:]

            if not self._compact(page_text).startswith(
                self._compact(anchor)
            ):
                mismatches.append(node)

        return mismatches

    # Find child ranges outside their parent ranges.
    def _find_parent_range_violations(
        self,
        nodes: list[DocumentNode],
        node_lookup: dict[str, DocumentNode],
    ) -> list[DocumentNode]:
        violations = []

        for node in nodes:
            parent = node_lookup.get(node.parent_id or "")

            if parent is None:
                continue

            node_start = node.start_page
            node_end = node.end_page
            parent_start = parent.start_page
            parent_end = parent.end_page

            if (
                node_start is None
                or node_end is None
                or parent_start is None
                or parent_end is None
            ):
                continue

            if (
                node_start < parent_start
                or node_end > parent_end
            ):
                violations.append(node)

        return violations

    # Find text anchors outside their physical parent.
    def _find_parent_position_violations(
        self,
        document: Document,
        nodes: list[DocumentNode],
        node_lookup: dict[str, DocumentNode],
    ) -> list[DocumentNode]:
        children_by_parent = {}

        for node in nodes:
            children_by_parent.setdefault(
                node.parent_id,
                [],
            ).append(node)

        for children in children_by_parent.values():
            children.sort(
                key=lambda child: child.sequence_no
            )

        if not document.pages:
            return []

        first_page = min(
            document.pages,
            key=lambda page: page.page_number,
        )
        last_page = max(
            document.pages,
            key=lambda page: page.page_number,
        )
        document_start = (first_page.page_number, 0)
        document_end = (
            last_page.page_number,
            len(last_page.text),
        )

        def get_end(node: DocumentNode) -> tuple[int, int]:
            if node.parent_id is None:
                return document_end

            siblings = children_by_parent.get(
                node.parent_id,
                [],
            )
            node_index = siblings.index(node)

            for sibling in siblings[node_index + 1:]:
                if (
                    sibling.start_page is not None
                    and sibling.start_character is not None
                ):
                    return (
                        sibling.start_page,
                        sibling.start_character,
                    )

            parent = node_lookup.get(node.parent_id)

            if parent is None:
                return document_end

            return get_end(parent)

        violations = []

        for node in nodes:
            if not self._requires_text_anchor(node):
                continue

            if (
                node.start_page is None
                or node.start_character is None
                or node.parent_id is None
            ):
                continue

            parent = node_lookup.get(node.parent_id)

            if parent is None:
                continue

            if parent.parent_id is None:
                parent_start = document_start
            elif (
                parent.start_page is not None
                and parent.start_character is not None
            ):
                parent_start = (
                    parent.start_page,
                    parent.start_character,
                )
            else:
                continue

            node_position = (
                node.start_page,
                node.start_character,
            )
            parent_end = get_end(parent)

            if not parent_start <= node_position < parent_end:
                violations.append(node)

        return violations

    # Remove case and layout whitespace for comparison.
    def _compact(self, text: str) -> str:
        return "".join(text.lower().split())
