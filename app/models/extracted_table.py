# ========================================
# File: extracted_table.py
# ========================================
#
# Purpose
# -------
# Represent one table extracted from one PDF page.
#
# Responsibilities
# ----------------
# - Preserve raw table text exactly as extracted.
# - Preserve table and cell bounding boxes.
# - Preserve empty placeholders created by merged cells.
#
# ========================================

# Import dataclass for the table data container.
from dataclasses import dataclass


# ==========================================================
# Shared Types
# ==========================================================

# Store left, top, right, and bottom coordinates.
BoundingBox = tuple[float, float, float, float]


# ==========================================================
# Extracted Table
# ==========================================================

# Hold the raw structure of one table found on one PDF page.
@dataclass
class ExtractedTable:

    # Store the one-based PDF page number.
    page_number: int

    # Store this table's one-based order on its page.
    table_number: int

    # Store the complete PDF page width.
    page_width: float

    # Store the complete PDF page height.
    page_height: float

    # Store the table fragment's outer coordinates.
    bounding_box: BoundingBox

    # Preserve None placeholders from merged cells.
    rows: list[list[str | None]]

    # Match optional geometry to every cell position.
    cell_bounding_boxes: list[list[BoundingBox | None]]

    # Return the largest cell count found in any row.
    @property
    def column_count(self) -> int:

        # Return zero safely when there are no rows.
        if not self.rows:
            return 0

        # Use the widest row as the table's raw column count.
        return max(len(row) for row in self.rows)
