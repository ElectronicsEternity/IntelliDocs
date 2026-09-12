# ========================================
# File: table_normalizer.py
# ========================================
#
# Purpose
# -------
# Normalize table geometry without subject assumptions.
#
# Responsibilities
# ----------------
# - Convert physical cells into logical spans.
# - Combine table fragments across PDF pages.
# - Remove exact repeated rows from later fragments.
# - Produce dimension-independent JSON.
#
# ========================================

# Import the extracted table model.
from app.models.extracted_table import ExtractedTable

# Import the complete logical-table model.
from app.models.logical_table import LogicalTable


# ==========================================================
# Table Normalizer
# ==========================================================

# Convert PDF geometry into generic table structures.
class TableNormalizer:

    # Return coordinates without near-duplicate values.
    def _unique_coordinates(
        self,
        values: list[float]
    ) -> list[float]:

        # Store stable coordinates in visual order.
        coordinates = []

        # Inspect each coordinate from smallest to largest.
        for value in sorted(values):

            # Identify the first coordinate in the list.
            is_first = not coordinates

            # Ignore differences caused only by rounding.
            is_distinct = (
                bool(coordinates)
                and abs(value - coordinates[-1]) > 0.1
            )

            # Keep each meaningfully different boundary.
            if is_first or is_distinct:
                coordinates.append(value)

        # Return the completed logical boundaries.
        return coordinates

    # Find the logical index nearest to one coordinate.
    def _coordinate_index(
        self,
        coordinates: list[float],
        value: float
    ) -> int:

        # Compare the value with every known boundary.
        return min(
            range(len(coordinates)),
            key=lambda index: abs(
                coordinates[index] - value
            ),
        )

    # Collapse extracted whitespace without changing meaning.
    def _clean_text(self, value: str | None) -> str:

        # Convert None to empty text and collapse whitespace.
        return " ".join((value or "").split())

    # Convert physical cells into logical table positions.
    def _build_cells(
        self,
        table: ExtractedTable
    ) -> list[dict]:

        # Store cells that own physical geometry.
        physical_cells = []

        # Process text rows with matching coordinate rows.
        for row, row_boxes in zip(
            table.rows,
            table.cell_bounding_boxes,
        ):

            # Process matching text and coordinate cells.
            for value, box in zip(row, row_boxes):

                # Ignore merged placeholders without geometry.
                if box is None:
                    continue

                # Keep the geometry and cleaned source text.
                physical_cells.append(
                    (box, self._clean_text(value))
                )

        # Return safely when no physical cells exist.
        if not physical_cells:
            return []

        # Collect every horizontal cell boundary.
        x_values = [
            value
            for box, _ in physical_cells
            for value in box[::2]
        ]

        # Collect every vertical cell boundary.
        y_values = [
            value
            for box, _ in physical_cells
            for value in box[1::2]
        ]

        # Convert coordinates into logical boundaries.
        x_coordinates = self._unique_coordinates(x_values)
        y_coordinates = self._unique_coordinates(y_values)

        # Store JSON-ready logical cells.
        cells = []

        # Convert every physical cell into logical spans.
        for box, value in physical_cells:

            # Locate its one-based starting row.
            row_start = self._coordinate_index(
                y_coordinates,
                box[1],
            ) + 1

            # Locate its one-based inclusive ending row.
            row_end = self._coordinate_index(
                y_coordinates,
                box[3],
            )

            # Locate its one-based starting column.
            column_start = self._coordinate_index(
                x_coordinates,
                box[0],
            ) + 1

            # Locate its one-based inclusive ending column.
            column_end = self._coordinate_index(
                x_coordinates,
                box[2],
            )

            # Store the text and its logical ownership.
            cells.append(
                {
                    "value": value,
                    "row_start": row_start,
                    "row_end": row_end,
                    "column_start": column_start,
                    "column_end": column_end,
                    "source_page": table.page_number,
                    "source_table": table.table_number,
                }
            )

        # Return every logical table cell.
        return cells

    # Return one row's exact structural signature.
    def _get_row_signature(
        self,
        cells: list[dict],
        row_number: int
    ) -> tuple[tuple[int, int, str], ...]:

        # Include cells beginning on the requested row.
        signature = [
            (
                cell["column_start"],
                cell["column_end"],
                cell["value"].casefold(),
            )
            for cell in cells
            if cell["row_start"] == row_number
        ]

        # Preserve the row's left-to-right structure.
        return tuple(sorted(signature))

    # Count exact leading rows repeated on a later page.
    def _get_repeated_row_count(
        self,
        first_cells: list[dict],
        following_cells: list[dict]
    ) -> int:

        # Return no repetition when either fragment is empty.
        if not first_cells or not following_cells:
            return 0

        # Limit comparison to the leading three rows.
        first_row_count = max(
            cell["row_end"] for cell in first_cells
        )
        following_row_count = max(
            cell["row_end"] for cell in following_cells
        )
        maximum = min(3, following_row_count)

        # Prefer the longest exact repeated sequence.
        for count in range(maximum, 0, -1):
            following_rows = tuple(
                self._get_row_signature(
                    following_cells,
                    row_number,
                )
                for row_number in range(1, count + 1)
            )

            # Search within the first fragment's header area.
            for start in range(
                1,
                min(3, first_row_count) - count + 2,
            ):
                first_rows = tuple(
                    self._get_row_signature(
                        first_cells,
                        row_number,
                    )
                    for row_number in range(
                        start,
                        start + count,
                    )
                )

                # Remove only exact text and span matches.
                if following_rows == first_rows:
                    return count

        # No leading rows repeat exactly.
        return 0

    # Build cells across all fragments of one table.
    def _build_logical_cells(
        self,
        logical_table: LogicalTable
    ) -> list[dict]:

        # Store cells in continuous logical row order.
        combined_cells = []

        # Keep first-fragment cells for repeat detection.
        first_cells = []

        # Begin the first fragment at row zero offset.
        row_offset = 0

        # Process every source fragment in page order.
        for index, fragment in enumerate(
            logical_table.fragments
        ):

            # Convert this fragment into logical cells.
            fragment_cells = self._build_cells(fragment)

            # Remember the first fragment structure.
            if index == 0:
                first_cells = fragment_cells

            # Detect exact repeated leading rows.
            repeated_rows = (
                self._get_repeated_row_count(
                    first_cells,
                    fragment_cells,
                )
                if index > 0
                else 0
            )

            # Exclude only completely repeated rows.
            retained_cells = [
                cell
                for cell in fragment_cells
                if cell["row_end"] > repeated_rows
            ]

            # Move cells into continuous row positions.
            for cell in retained_cells:
                shifted_cell = cell.copy()
                shifted_cell["row_start"] += (
                    row_offset - repeated_rows
                )
                shifted_cell["row_end"] += (
                    row_offset - repeated_rows
                )
                combined_cells.append(shifted_cell)

            # Continue after the last combined logical row.
            row_offset = max(
                (
                    cell["row_end"]
                    for cell in combined_cells
                ),
                default=row_offset,
            )

        # Return cells covering the complete logical table.
        return combined_cells

    # Group logical cells into dimension-independent rows.
    def _build_rows(
        self,
        cells: list[dict]
    ) -> list[dict]:

        # Return safely when the table contains no cells.
        if not cells:
            return []

        # Find the complete logical row count.
        row_count = max(cell["row_end"] for cell in cells)

        # Store every logical row band.
        rows = []

        # Process row bands from top to bottom.
        for row_number in range(1, row_count + 1):

            # Include cells spanning the current row band.
            row_cells = [
                cell.copy()
                for cell in cells
                if (
                    cell["row_start"] <= row_number
                    <= cell["row_end"]
                )
            ]

            # Preserve cells from left to right.
            row_cells.sort(
                key=lambda cell: (
                    cell["column_start"],
                    cell["column_end"],
                )
            )

            # Store the row and its active cells.
            rows.append(
                {
                    "row_number": row_number,
                    "cells": row_cells,
                }
            )

        # Return every logical row.
        return rows

    # Verify normalized values came from source cells.
    def _validate_cells(
        self,
        logical_table: LogicalTable,
        cells: list[dict]
    ) -> list[str]:

        # Store traceable source cell identities.
        source_cells = set()

        # Read every original fragment cell.
        for fragment in logical_table.fragments:
            for row in fragment.rows:
                for value in row:
                    source_cells.add(
                        (
                            fragment.page_number,
                            fragment.table_number,
                            self._clean_text(value),
                        )
                    )

        # Store untraceable normalized values.
        issues = []

        # Check every normalized cell against its source.
        for index, cell in enumerate(cells, start=1):
            identity = (
                cell["source_page"],
                cell["source_table"],
                cell["value"],
            )
            if identity not in source_cells:
                issues.append(
                    f"Cell {index} is absent from its source."
                )

        # Return every source-alignment issue.
        return issues

    # Normalize one complete logical table.
    def normalize_logical_table(
        self,
        logical_table: LogicalTable
    ) -> dict:

        # Build cells across all source fragments.
        cells = self._build_logical_cells(logical_table)

        # Build generic logical rows from cell spans.
        rows = self._build_rows(cells)

        # Confirm normalized values remain traceable.
        issues = self._validate_cells(
            logical_table,
            cells,
        )

        # Derive dimensions only from normalized geometry.
        row_count = max(
            (cell["row_end"] for cell in cells),
            default=0,
        )
        column_count = max(
            (cell["column_end"] for cell in cells),
            default=0,
        )

        # Return generic JSON without semantic guesses.
        return {
            "page_numbers": logical_table.page_numbers,
            "fragment_count": len(logical_table.fragments),
            "is_merged": logical_table.is_merged,
            "status": "normalized",
            "source_alignment_valid": not issues,
            "validation_issues": issues,
            "row_count": row_count,
            "column_count": column_count,
            "rows": rows,
            "cells": cells,
        }

    # Normalize one standalone extracted fragment.
    def normalize_table(
        self,
        table: ExtractedTable
    ) -> dict:

        # Wrap one fragment in the logical-table model.
        logical_table = LogicalTable(fragments=[table])

        # Use the same path as multi-page tables.
        return self.normalize_logical_table(logical_table)
