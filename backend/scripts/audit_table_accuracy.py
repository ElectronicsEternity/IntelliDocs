"""Offline source-character, column-placement and normalization coverage audit."""
import json
from collections import Counter
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pdfplumber
from PIL import Image, ImageDraw
from app.ingestion.pdfplumber_table_extractor import PdfPlumberTableExtractor
from app.ingestion.table_continuation_merger import TableContinuationMerger
from app.ingestion.table_gap_checker import TableGapChecker
from app.ingestion.table_normalizer import TableNormalizer

BASE = Path(__file__).resolve().parents[2] / 'backups/2026-09-17'
OUT = BASE / 'table-accuracy-audit'
REGIONS = {112: [(90,138,455,650)], 113: [(90,90,455,415),(85,494,460,650)],
           114: [(85,90,460,650)],115: [(85,90,460,650)],116: [(90,211,455,650)],
           117: [(90,90,455,650)],118: [(90,188,455,650)],
           **{p:[(90,90,455,650)] for p in range(119,128)}}


def inside(char, box):
    x, y = (char['x0']+char['x1'])/2, (char['top']+char['bottom'])/2
    return box[0] <= x < box[2] and box[1] <= y < box[3]


def compact(text):
    return ''.join(text.split())


def audit(label, filename, output_folder, regions=None):
    extractor, normalizer = PdfPlumberTableExtractor(), TableNormalizer()
    fragments, context, cell_checks, region_checks = [], {}, [], []
    with pdfplumber.open(BASE / 'pdfs' / filename) as document:
        for number, page in enumerate(document.pages, 1):
            tables = extractor.extract_page_tables(page, number, (regions or {}).get(number))
            fragments.extend(tables)
            context[number] = {'height': page.height, 'words': page.extract_words(), 'images': page.images}
            boxes = [box for table in tables for row in table.cell_bounding_boxes for box in row if box]
            for region in (regions or {}).get(number, []):
                chars = [c for c in page.chars if c['text'].strip() and inside(c, region)]
                missing = [c for c in chars if not any(inside(c, b) for b in boxes)]
                region_checks.append({'page': number, 'region': region, 'source_characters': len(chars),
                                      'uncovered_characters': len(missing),
                                      'uncovered_text': ''.join(c['text'] for c in missing)})
            for table in tables:
                for r, (values, row_boxes) in enumerate(zip(table.rows, table.cell_bounding_boxes), 1):
                    for col, (value, box) in enumerate(zip(values, row_boxes), 1):
                        if box is None:
                            continue
                        source = ''.join(c['text'] for c in page.chars if c['text'].strip() and inside(c, box))
                        missing = Counter(source) - Counter(compact(value or ''))
                        extra = Counter(compact(value or '')) - Counter(source)
                        cell_checks.append({'page': number, 'fragment': table.table_number, 'row': r, 'column': col,
                                            'bbox': box, 'value': value, 'source_characters': len(source),
                                            'missing_characters': dict(missing), 'extra_characters': dict(extra),
                                            'passed': not missing and not extra})
        groups = TableContinuationMerger().merge_tables(fragments, TableGapChecker(context))
        normalized = [normalizer.normalize_logical_table(g) for g in groups]
    saved = json.loads((BASE / output_folder / 'normalized-tables.json').read_text(encoding='utf-8'))
    assert normalized == saved, 'Audit differs from latest pipeline output'
    table_reports, lines = [], [f'# {label}: extracted rows', '']
    for i, (group, table) in enumerate(zip(groups, normalized), 1):
        raw = Counter((f.page_number, f.table_number, compact(v or '')) for f in group.fragments for row, boxes in zip(f.rows, f.cell_bounding_boxes) for v,b in zip(row, boxes) if b and compact(v or ''))
        retained = Counter((c['source_page'], c['source_table'], compact(c['value'])) for c in table['cells'] if compact(c['value']))
        removed = raw-retained
        table_reports.append({'table':i,'pages':table['page_numbers'],'columns':table['column_count'],
                              'rows':table['row_count'],'removed_during_normalization': [{'page':k[0],'fragment':k[1],'text':k[2],'count':v} for k,v in removed.items()],
                              'unexpected_normalized_cells':sum((retained-raw).values()),
                              'merge_reasons':group.merge_reasons})
        lines += [f"## Table {i}, pages {table['page_numbers']}", '', '| Row | Source page(s) | Cells by column |','|---|---|---|']
        for row in table['rows']:
            values = ' / '.join(f"C{c['column_start']}-{c['column_end']}: {c['value']}" for c in row['cells'])
            lines.append(f"| {row['row_number']} | {sorted({c['source_page'] for c in row['cells']})} | {values.replace('|','/')} |")
        lines.append('')
    (OUT / f'{label}-rows.md').write_text('\n'.join(lines),encoding='utf-8')
    pages = sorted({p for t in normalized for p in t['page_numbers']})
    for index in range(0,len(pages),2):
        pair = pages[index:index+2]
        images = [Image.open(BASE/output_folder/(f'geometry-{p}.png' if regions else f'page-{p}.png')).convert('RGB') for p in pair]
        sheet = Image.new('RGB',(sum(im.width for im in images),max(im.height for im in images)+30),'white')
        draw, left = ImageDraw.Draw(sheet), 0
        for p, im in zip(pair,images):
            draw.text((left+10,5),f'{label} PDF page {p}',fill='black')
            sheet.paste(im,(left,30)); left += im.width
        sheet.save(OUT/f'{label}-review-{index//2+1}.png')
    failures = [c for c in cell_checks if not c['passed']]
    report = {'tables':table_reports,'cells_checked':len(cell_checks),'cell_character_failures':failures,
              'region_coverage':region_checks,'page_breaks':[{'pages':g.page_numbers,'removed_headers':table_reports[i]['removed_during_normalization']} for i,g in enumerate(groups) if g.is_merged],
              'limitations':'Source character accounting is independent of table text extraction but uses the same PDF parser. It does not establish logical wrapped-row relationships or automatic borderless-region discovery.'}
    (OUT/f'{label}-audit.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps({'document':label,'tables':len(groups),'cells':len(cell_checks),'cell_failures':len(failures),
                      'uncovered_region_characters':sum(r['uncovered_characters'] for r in region_checks),
                      'normalization_removed':sum(len(t['removed_during_normalization']) for t in table_reports)}))


if __name__ == '__main__':
    OUT.mkdir(exist_ok=True)
    audit('akta','Akta Kerja 1955 (Akta 265).pdf','akta-borderless-table-test',REGIONS)
    audit('perintah','56. P.U. (A) 2022_140 Perintah Gaji Minimum 2022.pdf','perintah-table-continuation-test')
