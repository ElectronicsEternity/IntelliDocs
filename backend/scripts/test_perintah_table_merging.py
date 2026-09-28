"""Offline production table pipeline and legacy/new merge comparison."""
import json
import hashlib
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pdfplumber
from app.ingestion.pdf_table_processor import PDFTableProcessor
from app.ingestion.table_gap_checker import TableGapChecker


def main():
    base = Path(__file__).resolve().parents[2] / 'backups/2026-09-17'
    pdf = base / 'pdfs/56. P.U. (A) 2022_140 Perintah Gaji Minimum 2022.pdf'
    original_hash = hashlib.sha256(pdf.read_bytes()).hexdigest()
    processor = PDFTableProcessor()
    tables = processor.process(pdf)
    fragments, context = [], {}
    with pdfplumber.open(pdf) as document:
        for number, page in enumerate(document.pages, 1):
            fragments.extend(processor.extractor.extract_page_tables(page, number))
            context[number] = {'height': float(page.height), 'words': page.extract_words(), 'images': page.images}
    old = processor.merger.merge_tables(fragments)
    new = processor.merger.merge_tables(fragments, TableGapChecker(context))
    canonical = lambda groups: [processor.normalizer.normalize_logical_table(group) for group in groups]
    assert canonical(new) == tables
    assert hashlib.sha256(pdf.read_bytes()).hexdigest() == original_hash
    report = {'pdf_sha256': original_hash, 'fragments': len(fragments),
              'legacy_groups': [g.page_numbers for g in old], 'new_groups': [g.page_numbers for g in new],
              'normalized_output_unchanged': canonical(old) == tables,
              'source_alignment_passed': all(t['source_alignment_valid'] for t in tables),
              'tables': [{'pages': t['page_numbers'], 'rows': t['row_count'], 'columns': t['column_count']} for t in tables],
              'merge_evidence': [{'pages': g.page_numbers, 'reasons': g.merge_reasons, 'warnings': g.warnings} for g in new]}
    folder = base / 'perintah-table-continuation-test'
    folder.mkdir(exist_ok=True)
    (folder / 'normalized-tables.json').write_text(json.dumps(tables, indent=2, ensure_ascii=False), encoding='utf-8')
    (folder / 'validation-report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    import fitz
    with fitz.open(pdf) as document:
        for page in sorted({p for t in tables for p in t['page_numbers']}):
            document[page-1].get_pixmap().save(folder / f'page-{page}.png')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
