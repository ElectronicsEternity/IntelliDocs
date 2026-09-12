# ========================================
# File: table_terminal_renderer.py
# ========================================
#
# Purpose
# -------
# Render normalized table cells as readable terminal text.
#
# Responsibilities
# ----------------
# - Draw logical row and column spans.
# - Wrap long cell values.
# - Preserve horizontal and vertical merged cells.
# - Return display text without printing it directly.
#
# ========================================

# Import wrap for displaying long cell text.
from textwrap import wrap


# ==========================================================
# Table Terminal Renderer
# ==========================================================


class TableTerminalRenderer:

    # Store the maximum width allowed for one base column.
    def __init__(self, max_cell_width: int = 24):
        self.max_cell_width = max_cell_width

    # Wrap one value across readable terminal lines.
    def _wrap_cell(
        self,
        text: str,
        width: int
    ) -> list[str]:

        # Return one empty line for an empty cell.
        if not text:
            return [""]

        # Keep long text within its available cell width.
        return wrap(
            text,
            width=width,
            break_long_words=True,
        )

    # Calculate readable widths for base columns.
    def _get_column_widths(
        self,
        cells: list[dict],
        column_count: int
    ) -> list[int]:

        # Begin with a small width for every base column.
        widths = [3] * column_count

        # Use single-column values to size their columns.
        for cell in cells:

            # Calculate how many columns this cell occupies.
            span = (
                cell["column_end"]
                - cell["column_start"]
                + 1
            )

            # Let merged cells use combined column widths.
            if span != 1:
                continue

            # Convert the one-based column to a list index.
            index = cell["column_start"] - 1

            # Limit wide values for terminal readability.
            width = min(
                len(cell["value"]),
                self.max_cell_width,
            )

            # Retain the widest value in this column.
            widths[index] = max(widths[index], width)

        # Return all completed base-column widths.
        return widths

    # Return the printable width of a merged cell.
    def _get_merged_width(
        self,
        widths: list[int],
        start: int,
        end: int
    ) -> int:

        # Convert one-based columns into slice indexes.
        start_index = start - 1
        end_index = end

        # Count the inner borders removed by merging.
        removed_borders = 3 * (end - start)

        # Combine base widths and removed border space.
        return (
            sum(widths[start_index:end_index])
            + removed_borders
        )

    # Create one complete horizontal border.
    def _create_border(self, widths: list[int]) -> str:

        # Draw one bordered segment per base column.
        return "+" + "+".join(
            "-" * (width + 2) for width in widths
        ) + "+"

    # Find printable positions of column boundaries.
    def _get_boundary_positions(
        self,
        widths: list[int]
    ) -> list[int]:

        # The leftmost boundary begins at zero.
        positions = [0]

        # Move past each padded column and its border.
        for width in widths:
            positions.append(positions[-1] + width + 3)

        # Return every printable boundary position.
        return positions

    # Create a partial border around vertical merges.
    def _create_separator(
        self,
        widths: list[int],
        cells: list[dict],
        row_number: int
    ) -> str:

        # Begin with a complete horizontal border.
        characters = list(self._create_border(widths))

        # Locate printable column-boundary positions.
        positions = self._get_boundary_positions(widths)

        # Find cells continuing into the following row.
        for cell in cells:

            # Skip cells that do not cross this boundary.
            if not (
                cell["row_start"] <= row_number
                and cell["row_end"] > row_number
            ):
                continue

            # Convert its starting column to a list index.
            start = cell["column_start"] - 1

            # Its inclusive ending column is a boundary index.
            end = cell["column_end"]

            # Remove the border inside this continuing cell.
            for index in range(
                positions[start] + 1,
                positions[end],
            ):
                characters[index] = " "

        # Return the completed partial separator.
        return "".join(characters)

    # Find all cells occupying one logical row.
    def _get_row_cells(
        self,
        cells: list[dict],
        row_number: int
    ) -> list[dict]:

        # Store cells covering the requested row.
        row_cells = [
            cell.copy()
            for cell in cells
            if cell["row_start"] <= row_number
            <= cell["row_end"]
        ]

        # Hide text after a vertically merged cell begins.
        for cell in row_cells:
            if cell["row_start"] != row_number:
                cell["value"] = ""

        # Return cells from left to right.
        return sorted(
            row_cells,
            key=lambda cell: cell["column_start"],
        )

    # Render one logical row with merged cells.
    def _render_row(
        self,
        cells: list[dict],
        widths: list[int]
    ) -> list[str]:

        # Store width and wrapped text for every cell.
        prepared_cells = []

        # Prepare regular and merged cells in order.
        for cell in cells:

            # Calculate the complete merged-cell width.
            width = self._get_merged_width(
                widths,
                cell["column_start"],
                cell["column_end"],
            )

            # Wrap the value within that complete width.
            lines = self._wrap_cell(
                cell["value"],
                width,
            )

            # Keep display width and wrapped lines together.
            prepared_cells.append((width, lines))

        # Find the visual height needed by this row.
        row_height = max(
            len(lines) for _, lines in prepared_cells
        )

        # Store every printable line in this row.
        output_lines = []

        # Build each visual line from left to right.
        for line_index in range(row_height):

            # Start at the left table boundary.
            output = "|"

            # Add every prepared physical cell.
            for width, lines in prepared_cells:

                # Use blank padding after wrapped text ends.
                value = (
                    lines[line_index]
                    if line_index < len(lines)
                    else ""
                )

                # Add one padded cell and its right boundary.
                output += f" {value:<{width}} |"

            # Keep the completed visual row line.
            output_lines.append(output)

        # Return every visual line for this logical row.
        return output_lines

    # Render normalized cells as one complete table.
    def render(
        self,
        cells: list[dict],
        column_count: int
    ) -> str:

        # Return a clear result when no cells are available.
        if not cells:
            return "<EMPTY TABLE>"

        # Calculate readable base-column widths.
        widths = self._get_column_widths(
            cells,
            column_count,
        )

        # Find the final logical row in the table.
        row_count = max(cell["row_end"] for cell in cells)

        # Begin with the complete upper boundary.
        output_lines = [self._create_border(widths)]

        # Process every logical row from top to bottom.
        for row_number in range(1, row_count + 1):

            # Find cells covering the current row.
            row_cells = self._get_row_cells(
                cells,
                row_number,
            )

            # Add every rendered line from this row.
            output_lines.extend(
                self._render_row(row_cells, widths)
            )

            # Close the table after its final row.
            if row_number == row_count:
                output_lines.append(
                    self._create_border(widths)
                )
                continue

            # Add a separator preserving vertical merges.
            output_lines.append(
                self._create_separator(
                    widths,
                    cells,
                    row_number,
                )
            )

        # Return the complete terminal representation.
        return "\n".join(output_lines)
