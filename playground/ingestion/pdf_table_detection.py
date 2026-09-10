from pathlib import Path

import fitz


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PDF_FILE = (
    PROJECT_ROOT
    / "documents"
    / "56. P.U. (A) 2022_140 Perintah Gaji Minimum 2022.pdf"
)
TEST_PAGE_NUMBERS = [3, 4, 5]


def clean_cell(cell):
    # Make multiline table cells easier to inspect in one terminal row.
    return " ".join(cell.split()) if cell else ""


def main():
    print(f"PDF: {PDF_FILE.name}")
    print(f"Pages tested: {TEST_PAGE_NUMBERS}")
    print("\n=== PDF Table Detection Started ===")

    total_tables = 0

    with fitz.open(PDF_FILE) as document:
        for page_number in TEST_PAGE_NUMBERS:
            # PyMuPDF uses zero-based page indexes internally.
            page = document.load_page(page_number - 1)
            table_finder = page.find_tables()
            tables = table_finder.tables if table_finder is not None else []
            total_tables += len(tables)

            print("\n" + "=" * 100)
            print(f"Page {page_number} | Tables detected: {len(tables)}")

            for table_index, table in enumerate(tables, start=1):
                print("\n" + "-" * 100)
                print(f"Table {table_index} | Bounding box: {table.bbox}")

                # Each extracted row contains the cells detected across it.
                for row_index, row in enumerate(table.extract(), start=1):
                    cleaned_row = [clean_cell(cell) for cell in row]
                    print(f"Row {row_index}: {' | '.join(cleaned_row)}")

    print("\n=== PDF Table Detection Ended ===")
    print(f"\nTotal tables detected: {total_tables}")


if __name__ == "__main__":
    main()
