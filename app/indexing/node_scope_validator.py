# ========================================
# File: node_scope_validator.py
# ========================================
#
# Purpose
# -------
# Validate text scopes produced from mapped nodes.
#
# Responsibilities
# ----------------
# - Reject empty scope text.
# - Verify each scope begins at its anchor.
# - Verify adjacent scope boundaries meet exactly.
#
# ========================================

from dataclasses import dataclass


# ==========================================================
# Validation Result
# ==========================================================

@dataclass(frozen=True)
class NodeScopeValidationResult:
    empty_scopes: tuple[dict, ...]
    anchor_mismatches: tuple[dict, ...]
    boundary_violations: tuple[dict, ...]

    @property
    def is_valid(self) -> bool:
        return not any(
            (
                self.empty_scopes,
                self.anchor_mismatches,
                self.boundary_violations,
            )
        )


# ==========================================================
# Node Scope Validator
# ==========================================================

class NodeScopeValidator:

    # Validate every extracted node scope.
    def validate(
        self,
        scopes: list[dict],
    ) -> NodeScopeValidationResult:
        empty_scopes = []
        anchor_mismatches = []
        boundary_violations = []

        for index, scope in enumerate(scopes):
            if not scope["text"].strip():
                empty_scopes.append(scope)

            scope_text = self._compact(scope["text"])
            anchor_text = self._compact(
                scope["anchor_text"]
            )

            if not scope_text.startswith(anchor_text):
                anchor_mismatches.append(scope)

            if index == len(scopes) - 1:
                continue

            next_scope = scopes[index + 1]
            current_end = (
                scope["end_page"],
                scope["end_character"],
            )
            next_start = (
                next_scope["start_page"],
                next_scope["start_character"],
            )

            if current_end != next_start:
                boundary_violations.append(scope)

        return NodeScopeValidationResult(
            empty_scopes=tuple(empty_scopes),
            anchor_mismatches=tuple(
                anchor_mismatches
            ),
            boundary_violations=tuple(
                boundary_violations
            ),
        )

    # Remove case and layout whitespace for comparison.
    def _compact(self, text: str) -> str:
        return "".join(text.lower().split())
