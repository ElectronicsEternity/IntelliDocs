"""Run the existing production table processor offline and save review artifacts."""
import json
import hashlib
import time
from pathlib import Path
import sys
import argparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.ingestion.pdf_table_processor import PDFTableProcessor


def main(borderless=False):
    base = Path(__file__).resolve().parents[2] / 'backups/2026-09-17'
    pdf = base / 'pdfs/Akta Kerja 1955 (Akta 265).pdf'
    folder = base / ('akta-borderless-table-test' if borderless else 'akta-table-extraction-test')
    folder.mkdir(exist_ok=True)
    original_hash = hashlib.sha256(pdf.read_bytes()).hexdigest()
    started = time.monotonic()
    # Reviewed fixture regions in PDF points; document-specific values are kept
    # in this offline test, never in the generic production detector.
    regions = {112: [(90, 138, 455, 650)],
               113: [(90, 90, 455, 415), (85, 494, 460, 650)],
               114: [(85, 90, 460, 650)], 115: [(85, 90, 460, 650)],
               116: [(90, 211, 455, 650)], 117: [(90, 90, 455, 650)],
               118: [(90, 188, 455, 650)],
               **{p: [(90, 90, 455, 650)] for p in range(119, 128)}}
    tables = PDFTableProcessor().process(pdf, borderless_regions=regions if borderless else None)
    (folder / 'normalized-tables.json').write_text(json.dumps(tables, indent=2, ensure_ascii=False), encoding='utf-8')
    summary = []
    for i, table in enumerate(tables, 1):
        invalid_spans = [c for c in table['cells'] if not (1 <= c['row_start'] <= c['row_end'] <= table['row_count'] and 1 <= c['column_start'] <= c['column_end'] <= table['column_count'])]
        summary.append({'table': i, 'pages': table['page_numbers'], 'rows': table['row_count'],
                        'columns': table['column_count'], 'fragments': table['fragment_count'],
                        'source_alignment_valid': table['source_alignment_valid'],
                        'invalid_spans': len(invalid_spans), 'validation_issues': table['validation_issues']})
    import fitz
    hierarchy = json.loads((base / 'akta-section67-corrected-boundary-test/hierarchy-corrected.json').read_text(encoding='utf-8'))
    def walk(node):
        yield node
        for child in node['children']:
            yield from walk(child)
    hints = [n['start_page'] for n in walk(hierarchy) if n['type'] == 'TABLE']
    with fitz.open(pdf) as doc:
        for page in sorted({p for table in tables for p in table['page_numbers']} | set(hints)):
            doc[page-1].get_pixmap(matrix=fitz.Matrix(1.1, 1.1)).save(folder / f'page-{page}.png')
    if borderless:
        import pdfplumber
        from PIL import Image, ImageDraw
        from app.ingestion.borderless_table_detector import find_borderless_tables
        with pdfplumber.open(pdf) as doc:
            for page_number, boxes in regions.items():
                image = Image.open(folder / f'page-{page_number}.png').convert('RGB')
                draw = ImageDraw.Draw(image)
                for bbox in boxes:
                    for table in find_borderless_tables(doc.pages[page_number-1], bbox):
                        for cell in table.cells:
                            draw.rectangle(tuple(value * 1.1 for value in cell), outline='red', width=1)
                image.save(folder / f'geometry-{page_number}.png')
    assert hashlib.sha256(pdf.read_bytes()).hexdigest() == original_hash
    report = {'pdf_sha256': original_hash, 'elapsed_seconds': time.monotonic()-started,
              'table_count': len(tables), 'tables': summary, 'hierarchy_table_start_pages': hints,
              'scope': ('Reviewed PDF-region borderless fallback; inferred column gutters and physical text-line rows. ' if borderless else '') + 'Existing continuation merger and normalizer. No API/database/chunking/embedding operations. Source alignment alone does not prove extraction completeness.'}
    (folder / 'validation-report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    lines = ['# Akta Kerja table extraction', '', report['scope'], '', '| Table | Pages | Rows | Columns | Fragments | Source alignment | Invalid spans |', '|---|---|---|---|---|---|---|']
    for row in summary:
        lines.append(f"| {row['table']} | {row['pages']} | {row['rows']} | {row['columns']} | {row['fragments']} | {row['source_alignment_valid']} | {row['invalid_spans']} |")
    (folder / 'summary.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    print(json.dumps(report, indent=2), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--borderless', action='store_true')
    main(parser.parse_args().borderless)
