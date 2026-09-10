# ========================================
# File: table_continuation_merger.py
# ========================================
#
# Purpose
# -------
# Merge table fragments continued across PDF pages.
#
# Responsibilities
# ----------------
# - Compare table fragments on consecutive pages.
# - Check page-edge and column-alignment evidence.
# - Accept repeated-header or headerless continuations.
# - Flag uncertain links instead of guessing.
#
# ========================================

# Import the extracted table-fragment model.
from app.models.extracted_table import ExtractedTable

# Import the complete logical-table model.
from app.models.logical_table import LogicalTable


# ==========================================================
# Table Continuation Merger
# ==========================================================


class TableContinuationMerger:

    # Store safe geometric thresholds.
    def __init__(
        self,
        bottom_ratio: float = 0.85,
        top_ratio: float = 0.15,
        alignment_tolerance: float = 0.01,
        minimum_supporting_signals: int = 3
    ):
        self.bottom_ratio = bottom_ratio
        self.top_ratio = top_ratio
        self.alignment_tolerance = alignment_tolerance
        self.minimum_supporting_signals = (
            minimum_supporting_signals
        )

    # Collapse cell whitespace for stable comparison.
    def _clean_text(self, value: str | None) -> str:

        # Convert None safely and collapse whitespace.
        return " ".join((value or "").split())

    # Return readable values from one raw row.
    def _get_row_values(
        self,
        row: list[str | None]
    ) -> list[str]:

        # Remove empty and merged-placeholder values.
        return [
            text
            for value in row
            if (text := self._clean_text(value))
        ]

    # Return normalized non-empty rows for comparison.
    def _get_normalized_rows(
        self,
        table: ExtractedTable
    ) -> list[list[str]]:

        # Store readable rows in original order.
        normalized_rows = []

        # Normalize every non-empty extracted row.
        for row in table.rows:

            # Load non-empty readable values.
            values = self._get_row_values(row)

            # Ignore completely empty extracted rows.
            if not values:
                continue

            # Normalize text case for comparison.
            normalized_rows.append(
                [value.casefold() for value in values]
            )

        # Return every normalized non-empty row.
        return normalized_rows

    # Return True when the next table repeats headers.
    def _has_repeated_header(
        self,
        current: ExtractedTable,
        following: ExtractedTable
    ) -> bool:

        # Load readable rows from both fragments.
        current_rows = self._get_normalized_rows(current)
        following_rows = self._get_normalized_rows(
            following
        )

        # Repetition requires rows in both fragments.
        if not current_rows or not following_rows:
            return False

        # Compare up to three leading rows exactly.
        maximum = min(
            3,
            len(current_rows),
            len(following_rows),
        )

        # Prefer the longest repeated leading sequence.
        for count in range(maximum, 0, -1):
            if current_rows[:count] == following_rows[:count]:
                return True

        # No leading rows repeat across these fragments.
        return False

    # Return sorted coordinates without rounding duplicates.
    def _unique_coordinates(
        self,
        values: list[float]
    ) -> list[float]:

        # Store stable coordinates in visual order.
        coordinates = []

        # Ignore near-duplicates caused by PDF rounding.
        for value in sorted(values):
            is_first = not coordinates
            is_distinct = (
                bool(coordinates)
                and abs(value - coordinates[-1]) > 0.1
            )
            if is_first or is_distinct:
                coordinates.append(value)

        # Return every distinct coordinate.
        return coordinates

    # Find the nearest logical coordinate index.
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

    # Return every physical cell box in one fragment.
    def _get_cell_boxes(
        self,
        table: ExtractedTable
    ) -> list[tuple[float, float, float, float]]:

        # Exclude merged placeholders without geometry.
        return [
            box
            for row in table.cell_bounding_boxes
            for box in row
            if box is not None
        ]

    # Build merged-cell span patterns for logical rows.
    def _get_row_span_signatures(
        self,
        table: ExtractedTable
    ) -> list[tuple[tuple[int, int], ...]]:

        # Load all physical cell rectangles.
        boxes = self._get_cell_boxes(table)

        # Return no signatures when geometry is absent.
        if not boxes:
            return []

        # Build all logical horizontal boundaries.
        x_coordinates = self._unique_coordinates(
            [
                value
                for box in boxes
                for value in (box[0], box[2])
            ]
        )

        # Build all logical vertical boundaries.
        y_coordinates = self._unique_coordinates(
            [
                value
                for box in boxes
                for value in (box[1], box[3])
            ]
        )

        # Store the span pattern covering each row band.
        signatures = []

        # Process every logical row from top to bottom.
        for index in range(len(y_coordinates) - 1):
            top = y_coordinates[index]
            bottom = y_coordinates[index + 1]
            spans = []

            # Find cells covering this complete row band.
            for box in boxes:
                covers_band = (
                    box[1] <= top + 0.1
                    and box[3] >= bottom - 0.1
                )
                if not covers_band:
                    continue

                # Convert its coordinates into column spans.
                start = self._coordinate_index(
                    x_coordinates,
                    box[0],
                )
                end = self._coordinate_index(
                    x_coordinates,
                    box[2],
                )
                spans.append((start, end))

            # Preserve the complete left-to-right pattern.
            signatures.append(tuple(sorted(spans)))

        # Return every logical row's cell-span pattern.
        return signatures

    # Check the following row against earlier row shapes.
    def _has_compatible_row_structure(
        self,
        current: ExtractedTable,
        following: ExtractedTable
    ) -> bool:

        # Build resolved span patterns for both fragments.
        current_rows = self._get_row_span_signatures(current)
        following_rows = self._get_row_span_signatures(
            following
        )

        # Both fragments require physical row geometry.
        if not current_rows or not following_rows:
            return False

        # Compare the next first row with recent current rows
        # returns boolean
        return following_rows[0] in current_rows[-3:]

    # Return distinct horizontal cell boundaries.
    def _get_x_boundaries(
        self,
        table: ExtractedTable
    ) -> list[float]:

        # Collect every left and right coordinate.
        values = [
            coordinate
            for row in table.cell_bounding_boxes
            for box in row
            if box is not None
            for coordinate in (box[0], box[2])
        ]

        # Return every distinct horizontal boundary.
        return self._unique_coordinates(values)

    # Check whether fragment columns line up horizontally.
    def _columns_align(
        self,
        current: ExtractedTable,
        following: ExtractedTable
    ) -> bool:

        # Load both fragments' horizontal boundaries.
        current_x = self._get_x_boundaries(current)
        following_x = self._get_x_boundaries(following)

        # Both fragments require real column boundaries.
        if not current_x or not following_x:
            return False

        # Convert current boundaries into page ratios.
        current_ratios = [
            value / current.page_width
            for value in current_x
        ]

        # Convert following boundaries into page ratios.
        following_ratios = [
            value / following.page_width
            for value in following_x
        ]

        # Compare the smaller boundary set with the larger.
        smaller, larger = sorted(
            [current_ratios, following_ratios],
            key=len,
        )

        # Count boundaries with a nearby counterpart.
        matched = sum(
            any(
                abs(value - candidate)
                <= self.alignment_tolerance
                for candidate in larger
            )
            for value in smaller
        )

        # Require at least three quarters to align.
        alignment_ratio = matched / len(smaller)

        # Allow one boundary to differ through merged cells.
        return alignment_ratio >= 0.75

    # Check whether overall table widths remain compatible.
    def _table_shapes_match(
        self,
        current: ExtractedTable,
        following: ExtractedTable
    ) -> bool:

        # Measure table widths relative to their pages.
        current_width = (
            current.bounding_box[2]
            - current.bounding_box[0]
        ) / current.page_width

        # Measure the following relative table width.
        following_width = (
            following.bounding_box[2]
            - following.bounding_box[0]
        ) / following.page_width

        # Reject a materially different overall structure.
        return (
            abs(current_width - following_width)
            <= self.alignment_tolerance
        )

    # Check whether the current table reaches page bottom.
    def _ends_near_bottom(
        self,
        table: ExtractedTable
    ) -> bool:

        # Measure the current table's bottom position.
        current_bottom = (
            table.bounding_box[3]
            / table.page_height
        )

        # Apply the configured lower-page threshold.
        return current_bottom >= self.bottom_ratio

    # Check whether the following table begins near page top.
    def _starts_near_top(
        self,
        table: ExtractedTable
    ) -> bool:

        # Measure the following table's top position.
        following_top = (
            table.bounding_box[1]
            / table.page_height
        )

        # Apply the configured upper-page threshold.
        return following_top <= self.top_ratio

    # Evaluate all continuation signals for one pair.
    def _evaluate_pair(
        self,
        current: ExtractedTable,
        following: ExtractedTable,
        tables: list[ExtractedTable]
    ) -> tuple[bool, list[str], bool, int]:

        # Confirm that page numbers are consecutive.
        consecutive = (
            following.page_number
            == current.page_number + 1
        )

        # Find the final table number on the current page.
        final_number = max(
            table.table_number
            for table in tables
            if table.page_number == current.page_number
        )

        # Require the last table followed by the first.
        page_order = (
            current.table_number == final_number
            and following.table_number == 1
        )

        # Compare their basic logical column counts.
        same_columns = (
            current.column_count == following.column_count
        )

        # Check their physical horizontal alignment.
        aligned = self._columns_align(current, following)

        # Check whether current reaches the page bottom.
        ends_near_bottom = self._ends_near_bottom(current)

        # Check whether following begins near the page top.
        starts_near_top = self._starts_near_top(following)

        # Reject a materially different table structure.
        same_structure = self._table_shapes_match(
            current,
            following,
        )

        # Compare the next row with recent row structures.
        compatible_row = self._has_compatible_row_structure(
            current,
            following,
        )

        # Detect a repeated table header if present.
        repeated_header = self._has_repeated_header(
            current,
            following,
        )

        # A compatible row supports headerless continuation.
        headerless_structure = (
            not repeated_header and compatible_row
        )

        # Collect readable evidence for inspection.
        reasons = []

        # Add every continuation signal that passed.
        if consecutive:
            reasons.append("consecutive pages")
        if page_order:
            reasons.append("last table to first table")
        if same_columns:
            reasons.append("matching column count")
        if aligned:
            reasons.append("aligned column boundaries")
        if ends_near_bottom:
            reasons.append("current table reaches page bottom")
        if starts_near_top:
            reasons.append("next table begins near page top")
        if compatible_row:
            reasons.append("compatible row structure")
        if same_structure:
            reasons.append("matching overall table structure")
        if repeated_header:
            reasons.append("matching repeated header")
        elif headerless_structure:
            reasons.append(
                "headerless structural continuation"
            )

        # Require all four physical boundary conditions.
        mandatory_match = all(
            [
                consecutive,
                page_order,
                ends_near_bottom,
                starts_near_top,
            ]
        )

        # Count independent structural evidence signals.
        supporting_signals = [
            same_columns,
            aligned,
            compatible_row,
            same_structure,
            repeated_header,
        ]

        # Count only supporting checks that passed.
        support_count = sum(supporting_signals)

        # Require sufficient support after mandatory checks.
        enough_support = (
            support_count
            >= self.minimum_supporting_signals
        )

        # A repeated header is sufficient after mandatory checks.
        # A headerless fragment still needs enough support.
        should_merge = (
            mandatory_match
            and (
                repeated_header
                or (
                    headerless_structure
                    and enough_support
                )
            )
        )

        # Return the decision and its measured evidence.
        return (
            should_merge,
            reasons,
            mandatory_match,
            support_count,
        )

    # Merge confirmed fragments into logical tables.
    def merge_tables(
        self,
        tables: list[ExtractedTable]
    ) -> list[LogicalTable]:

        # Return safely when no tables were extracted.
        if not tables:
            return []

        # Process fragments in document reading order.
        ordered = sorted(
            tables,
            key=lambda table: (
                table.page_number,
                table.table_number,
            ),
        )

        # Begin the first logical table group.
        logical_tables = [LogicalTable([ordered[0]])]

        # Compare every later fragment with its predecessor.
        for following in ordered[1:]:

            # Load the latest fragment in the active group.
            current_group = logical_tables[-1]
            current = current_group.fragments[-1]

            # Evaluate whether both fragments form one table.
            evaluation = self._evaluate_pair(
                current,
                following,
                ordered,
            )

            # Unpack the complete merge evaluation.
            (
                should_merge,
                reasons,
                mandatory_match,
                support_count,
            ) = evaluation

            # Add confirmed continuation to the active group.
            if should_merge:
                current_group.fragments.append(following)
                current_group.merge_reasons.append(reasons)
                continue

            # Warn when boundaries pass but support does not.
            if mandatory_match:
                warning = (
                    f"Possible continuation from page "
                    f"{current.page_number} to page "
                    f"{following.page_number}: "
                    f"support {support_count}/5; "
                    f"{', '.join(reasons)}"
                )
                current_group.warnings.append(warning)

            # Begin a separate logical table group.
            logical_tables.append(LogicalTable([following]))

        # Return every confirmed logical table.
        return logical_tables
