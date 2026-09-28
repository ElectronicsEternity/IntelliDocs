"""Extract tables from page regions supplied by a validated table profile."""

from pathlib import Path

import pdfplumber

from app.ingestion.pdfplumber_table_extractor import PdfPlumberTableExtractor
from app.ingestion.borderless_table_detector import find_borderless_tables
from app.ingestion.table_normalizer import TableNormalizer
from app.models.logical_table import LogicalTable


class ProfileGuidedTableProcessor:
    def __init__(self):
        self.extractor = PdfPlumberTableExtractor(skip_first_page=False)
        self.normalizer = TableNormalizer()

    @staticmethod
    def _pdf_box(page, region):
        return (
            page.width * region["left"] / 1000,
            page.height * region["top"] / 1000,
            page.width * region["right"] / 1000,
            page.height * region["bottom"] / 1000,
        )

    @staticmethod
    def _overlaps(left, right):
        return (
            left[0] < right[2] and left[2] > right[0]
            and left[1] < right[3] and left[3] > right[1]
        )

    @staticmethod
    def _refine_borderless_box(page, box, table):
        """Remove routine margins and start at a printed column heading when found."""
        left, top, right, bottom = box
        top = max(top, float(page.height) * 0.12)
        bottom = min(bottom, float(page.height) * 0.895)
        if page.page_number == table["start_page"]:
            first_heading = next(
                (heading for heading in table["column_headings"] if heading.strip()), ""
            )
            first_token = first_heading.split()[0].casefold().strip(".,:;")
            matches = [
                word for word in page.extract_words()
                if left <= word["x0"] <= right and top <= word["top"] <= bottom
                and word["text"].casefold().strip(".,:;") == first_token
            ]
            if matches:
                top = max(top, float(matches[0]["top"]) - 5)
        return left, top, right, bottom

    def _candidates(self, page, page_number, table, region):
        box = self._pdf_box(page, region)
        style = table["border_style"]
        candidates = []
        if style in {"bordered", "mixed", "uncertain"}:
            # Detect complete ruled tables first. The profile region selects the
            # correct table but never clips away its outer border.
            for detected in page.find_tables():
                if not self._overlaps(detected.bbox, box):
                    continue
                candidates.append(
                    self.extractor._convert_table(
                        detected, page_number, len(candidates) + 1,
                        float(page.width), float(page.height),
                    )
                )
        if style in {"borderless", "mixed", "uncertain"}:
            refined = self._refine_borderless_box(page, box, table)
            for detected in find_borderless_tables(page, refined):
                candidates.append(
                    self.extractor._convert_table(
                        detected, page_number, len(candidates) + 1,
                        float(page.width), float(page.height),
                    )
                )
        expected = table["column_count"]
        exact = [candidate for candidate in candidates if candidate.column_count == expected]
        return exact or candidates

    def process(self, pdf_path: Path, profile: dict) -> tuple[list[dict], list[dict]]:
        normalized, diagnostics = [], []
        with pdfplumber.open(pdf_path) as document:
            for table in profile["tables"]:
                fragments = []
                page_diagnostics = []
                for region in table["page_regions"]:
                    page = document.pages[region["page"] - 1]
                    candidates = self._candidates(page, region["page"], table, region)
                    selected = candidates[0] if len(candidates) == 1 else None
                    if selected:
                        fragments.append(selected)
                    page_diagnostics.append({
                        "page": region["page"],
                        "candidate_count": len(candidates),
                        "candidate_columns": [candidate.column_count for candidate in candidates],
                        "selected": selected is not None,
                    })
                result = None
                if len(fragments) == len(table["page_regions"]):
                    result = self.normalizer.normalize_logical_table(
                        LogicalTable(
                            fragments=fragments,
                            merge_reasons=[["validated table-profile page range"]]
                            * max(0, len(fragments) - 1),
                        )
                    )
                    normalized.append(result)
                diagnostics.append({
                    "table_id": table["table_id"],
                    "title": table["title"],
                    "expected_columns": table["column_count"],
                    "expected_header_rows": table["header_row_count"],
                    "expected_data_rows": table["data_row_count"],
                    "border_style": table["border_style"],
                    "pages": page_diagnostics,
                    "extracted": result is not None,
                    "extracted_columns": result["column_count"] if result else None,
                    "extracted_physical_rows": result["row_count"] if result else None,
                })
        return normalized, diagnostics
