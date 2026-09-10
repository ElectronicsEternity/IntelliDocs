# ========================================
# File: logical_table.py
# ========================================
#
# Purpose
# -------
# Represent one table that may span several PDF pages.
#
# Responsibilities
# ----------------
# - Keep ordered table fragments together.
# - Preserve reasons supporting continuation merges.
# - Preserve warnings for uncertain continuations.
#
# ========================================

# Import dataclass for the logical table container.
from dataclasses import dataclass, field

# Import the source table-fragment model.
from app.models.extracted_table import ExtractedTable


# ==========================================================
# Logical Table
# ==========================================================


@dataclass
class LogicalTable:

    # Store fragments in page and table order.
    fragments: list[ExtractedTable]

    # Store evidence supporting completed merges.
    merge_reasons: list[list[str]] = field(
        default_factory=list
    )

    # Store uncertain continuation descriptions.
    warnings: list[str] = field(default_factory=list)

    # Return all pages occupied by this logical table.
    @property
    def page_numbers(self) -> list[int]:

        # Preserve fragment page order without duplicates.
        return list(
            dict.fromkeys(
                fragment.page_number
                for fragment in self.fragments
            )
        )

    # Return the largest fragment column count.
    @property
    def column_count(self) -> int:

        # Return zero safely when no fragments exist.
        if not self.fragments:
            return 0

        # Use the widest source table fragment.
        return max(
            fragment.column_count
            for fragment in self.fragments
        )

    # Return True when this table spans multiple pages.
    @property
    def is_merged(self) -> bool:

        # More than one fragment confirms a merge.
        return len(self.fragments) > 1
