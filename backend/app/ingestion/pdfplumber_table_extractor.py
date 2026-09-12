# ========================================
# File: pdfplumber_table_extractor.py
# ========================================
#
# Purpose
# -------
# Extract clean table structures from PDF pages.
#
# Responsibilities
# ----------------
# - Detect tables using pdfplumber.
# - Remove false rows outside table boundaries.
# - Preserve raw row and cell values.
# - Preserve table and cell bounding boxes.
# - Return application-owned table objects.
#
# ========================================

# Import Any for pdfplumber page objects.
from typing import Any

# Import the application-owned table model.
from app.models.extracted_table import (
    BoundingBox,
    ExtractedTable,
)


# ==========================================================
# PdfPlumber Table Extractor
# ==========================================================


class PdfPlumberTableExtractor:

    # Store document-level table extraction rules.
    def __init__(
        self,
        skip_first_page: bool = True
    ):

        # Skip cover-page layouts unless explicitly enabled.
        self.skip_first_page = skip_first_page

    # Return True when a row has no visible cell text.
    def _is_empty_row(
        self,
        row: list[str | None]
    ) -> bool:

        # Check every cell after safely converting it to text.
        return all(not (cell or "").strip() for cell in row)

    # Remove false rows outside the real table boundary.
    def _clean_rows(
        self,
        rows: list[list[str | None]],
        boxes: list[list[BoundingBox | None]]
    ) -> tuple[
        list[list[str | None]],
        list[list[BoundingBox | None]],
    ]:

        # Store rows that belong to the real table.
        clean_rows = []

        # Keep geometry aligned with each retained row.
        clean_boxes = []

        # Inspect the extracted text and geometry together.
        for row, row_boxes in zip(rows, boxes):

            # Ignore empty rows before the first real row.
            if self._is_empty_row(row) and not clean_rows:
                continue

            # Treat a later empty row as the table's end.
            if self._is_empty_row(row):
                break

            # Keep the current meaningful table row.
            clean_rows.append(row)

            # Keep the matching cell coordinates.
            clean_boxes.append(row_boxes)

        # Return aligned text rows and coordinate rows.
        return clean_rows, clean_boxes

    # Recalculate the boundary around retained cells.
    def _calculate_bounding_box(
        self,
        boxes: list[list[BoundingBox | None]],
        fallback: BoundingBox
    ) -> BoundingBox:

        # Combine all existing cell boxes into one list.
        cells = []

        # Visit every retained coordinate row.
        for row in boxes:

            # Visit every possible cell coordinate.
            for cell in row:

                # Exclude merged-cell placeholders.
                if cell is not None:
                    cells.append(cell)

        # Retain pdfplumber's boundary if no cells remain.
        if not cells:
            return fallback

        # Enclose every retained cell in one rectangle.
        return (
            min(cell[0] for cell in cells),
            min(cell[1] for cell in cells),
            max(cell[2] for cell in cells),
            max(cell[3] for cell in cells),
        )

    # Convert one detected table into our table model.
    def _convert_table(
        self,
        detected_table: Any,
        page_number: int,
        table_number: int,
        page_width: float,
        page_height: float
    ) -> ExtractedTable:

        # Extract raw text with merged-cell placeholders.
        rows = detected_table.extract()

        # Collect geometry matching each extracted row.
        cell_boxes = []

        # Process detected rows in visual order.
        for detected_row in detected_table.rows:

            # Collect geometry for this row.
            row_boxes = []

            # Convert every cell coordinate into a tuple.
            for cell in detected_row.cells:

                # Preserve merged-cell placeholders.
                if cell is None:
                    row_boxes.append(None)
                    continue

                # Store left, top, right, and bottom.
                row_boxes.append(
                    (
                        float(cell[0]),
                        float(cell[1]),
                        float(cell[2]),
                        float(cell[3]),
                    )
                )

            # Keep this completed geometry row.
            cell_boxes.append(row_boxes)

        # Convert pdfplumber's outer table boundary.
        raw_box: BoundingBox = (
            float(detected_table.bbox[0]),
            float(detected_table.bbox[1]),
            float(detected_table.bbox[2]),
            float(detected_table.bbox[3]),
        )

        # Remove rows outside the real table boundary.
        rows, cell_boxes = self._clean_rows(
            rows,
            cell_boxes,
        )

        # Recalculate the boundary after row cleanup.
        table_box = self._calculate_bounding_box(
            cell_boxes,
            raw_box,
        )

        # Return the cleaned application table model.
        return ExtractedTable(
            page_number=page_number,
            table_number=table_number,
            page_width=page_width,
            page_height=page_height,
            bounding_box=table_box,
            rows=rows,
            cell_bounding_boxes=cell_boxes,
        )

    # Extract every clean table found on one PDF page.
    def extract_page_tables(
        self,
        page: Any,
        page_number: int
    ) -> list[ExtractedTable]:

        # Ignore cover-page layouts under the default rule.
        if self.skip_first_page and page_number == 1:
            return []

        # Ask pdfplumber to detect table candidates.
        detected_tables = page.find_tables()

        # Collect cleaned application table models.
        extracted_tables = []

        # Convert candidates in their original page order.
        for number, table in enumerate(
            detected_tables,
            start=1,
        ):

            # Convert and clean the current table candidate.
            extracted_table = self._convert_table(
                detected_table=table,
                page_number=page_number,
                table_number=number,
                page_width=float(page.width),
                page_height=float(page.height),
            )

            # Exclude candidates containing no real rows.
            if extracted_table.rows:
                extracted_tables.append(extracted_table)

        # Return every clean table from this page.
        return extracted_tables
