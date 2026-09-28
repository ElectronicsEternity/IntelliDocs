"""Read-only offline hierarchy diagnostics; no API or database operations."""
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.indexing.candidate_page_mapper import CandidatePageMapper
from app.indexing.document_profile_validator import DocumentProfileValidator
from app.ingestion.parser import PDFParser


ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'backups' / '2026-09-17'


def entries(tree, parent=()):
    path = parent + (f"{tree['type']} {tree.get('identifier', '')} {tree.get('title', '')}".strip(),)
    yield tree, path
    for child in tree['children']:
        yield from entries(child, path)


def main():
    pdf = BASE / 'pdfs' / 'Akta Kerja 1955 (Akta 265).pdf'
    document = PDFParser(pdf).extract_text('offline-review', 'offline-review', pdf.name)
    pages = {p.page_number: p for p in document.pages}
    output = BASE / 'akta-gpt5-vs-gpt56-high-review'
    output.mkdir(exist_ok=True)
    results = {}
    for name, folder in [('GPT-5 initial v4', 'akta-page-profile-experiment-v4'),
                         ('GPT-5.6 high initial', 'akta-gpt56-high-once')]:
        source = BASE / folder / 'hierarchy-with-pages.json'
        tree = json.loads(source.read_text(encoding='utf-8'))
        raw = json.loads((BASE / folder / 'response.json').read_text(encoding='utf-8'))
        assert hashlib.sha256(pdf.read_bytes()).hexdigest() == raw['metadata']['pdf_hash']
        checks, duplicates = [], []
        for node, path in entries(tree):
            groups = defaultdict(list)
            for c in node['children']:
                groups[(c['type'], c['identifier'], c['title'])].append(c.get('start_page'))
            duplicates.extend({'parent': list(path), 'key': list(k), 'pages': v}
                              for k, v in groups.items() if len(v) > 1)
            if node['type'] in ('DOCUMENT', 'TABLE'):
                continue
            anchor = node['title'].strip() or node['identifier'].strip()
            if not anchor:
                continue
            page = node.get('start_page')
            matches = CandidatePageMapper._matches(anchor, [pages[page]], identifier=not bool(node['title'].strip())) if page in pages else []
            other = CandidatePageMapper._matches(anchor, document.pages, identifier=not bool(node['title'].strip())) if not matches else []
            checks.append({'path': list(path), 'type': node['type'], 'identifier': node['identifier'],
                           'title': node['title'], 'claimed_page': page,
                           'matches_on_claimed_page': len(matches),
                           'other_candidate_pages': sorted({p for p, _ in other}),
                           'status': 'text supported; heading location not proven' if matches else 'needs review'})
        results[name] = {'source': str(source), 'model': raw['metadata']['model'],
                         'counts': dict(Counter(n['type'] for n, _ in entries(tree))),
                         'validation_errors': list(DocumentProfileValidator().validate(tree).errors),
                         'duplicate_groups': duplicates, 'anchor_checks': checks,
                         'common_level_checks': [c for c in checks if c['type'] not in ('SUBSECTION', 'CLAUSE')]}
    report = {'pages': document.total_pages, 'results': results,
              'limitations': 'Text presence is not heading/page accuracy. Earlier JSON is not ground truth. Fine-grained coverage differs. No repairs or database mutations.'}
    (output / 'comparison.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    lines = ['# Offline hierarchy comparison', '', report['limitations'], '',
             '| Output | Total nodes | Common-level anchors supported | Common-level anchors needing review | Duplicate groups |',
             '|---|---:|---:|---:|---:|']
    for name, r in results.items():
        common = r['common_level_checks']
        lines.append(f"| {name} | {sum(r['counts'].values())} | {sum(c['matches_on_claimed_page'] > 0 for c in common)}/{len(common)} | {sum(not c['matches_on_claimed_page'] for c in common)} | {len(r['duplicate_groups'])} |")
        lines.extend(['', '## ' + name, '', '| Node | Claimed page | Candidate pages |', '|---|---:|---|'])
        for c in r['anchor_checks']:
            if not c['matches_on_claimed_page']:
                label = ' > '.join(c['path']).replace('|', '\\|')
                lines.append(f"| {label} | {c['claimed_page']} | {c['other_candidate_pages']} |")
    (output / 'comparison.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps({name: {'counts': r['counts'], 'common_supported': sum(c['matches_on_claimed_page'] > 0 for c in r['common_level_checks']),
                            'common_total': len(r['common_level_checks']), 'needs_review': [c for c in r['common_level_checks'] if not c['matches_on_claimed_page']],
                            'duplicates': r['duplicate_groups']} for name, r in results.items()}, indent=2, ensure_ascii=True))
    # Render only suspect pages for visual review; preserve original files.
    import fitz
    rendered = output / 'page-previews'
    rendered.mkdir(exist_ok=True)
    with fitz.open(pdf) as source_pdf:
        for number in (40, 41, 53, 82, 94, 95, 101, 103, 108):
            source_pdf[number - 1].get_pixmap(matrix=fitz.Matrix(1.3, 1.3)).save(str(rendered / f'page-{number}.png'))


if __name__ == '__main__':
    main()
