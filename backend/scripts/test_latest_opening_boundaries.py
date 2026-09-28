"""Offline title/opening confirmation on the latest saved full hierarchy."""
import hashlib
import json
from contextlib import redirect_stdout
from io import StringIO

from compare_hierarchy_boundaries import BASE, run
from app.ingestion.parser import PDFParser


def main():
    source = BASE / 'akta-gpt56-high-full-opening-texts/hierarchy-with-pages.json'
    pdf = BASE / 'pdfs/Akta Kerja 1955 (Akta 265).pdf'
    hashes = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in (source, pdf)}
    tree = json.loads(source.read_text(encoding='utf-8'))
    metadata = json.loads((source.parent / 'response.json').read_text(encoding='utf-8'))['metadata']
    assert hashes[pdf] == metadata['pdf_hash']
    document = PDFParser(pdf).extract_text('offline', 'offline', pdf.name)
    with redirect_stdout(StringIO()):
        result = run(tree, document, forward_dfs=True)
    result['input_sha256'] = {str(p): h for p, h in hashes.items()}
    result['scope'] = 'Offline diagnostic only: no API, database, ingestion, chunks or embeddings. Tables not geometrically validated.'
    positions = {p['id']: p for p in result['positions']}
    result['unresolved_context'] = []
    def walk(raw):
        yield raw
        for child in raw['children']:
            yield from walk(child)
    raw_nodes = {'node-' + str(i): n for i, n in enumerate(walk(tree))}
    for failure in result['resolution']['unresolved']:
        raw = raw_nodes[failure['id']]
        result['unresolved_context'].append({**failure, 'path': positions[failure['id']]['path'],
                                             'start_page': raw.get('start_page'), 'opening_text': raw.get('opening_text')})
    assert all(hashlib.sha256(p.read_bytes()).hexdigest() == h for p, h in hashes.items())
    folder = BASE / 'akta-title-opening-boundary-test'
    folder.mkdir(exist_ok=True)
    (folder / 'validation-report.json').write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
    lines = ['# Title and opening-text boundary validation', '', result['scope'], '',
             '## Summary', '', json.dumps(result['summary'], indent=2), '',
             'Scope extraction: ' + str(result['scope_error']), '',
             '## Unresolved nodes', '', '| Node | Opening text | Reason |', '|---|---|---|']
    for entry in result['unresolved_context']:
        lines.append('| ' + ' > '.join(entry['path']).replace('|', '/') + ' | ' + str(entry['opening_text']).replace('|', '/') + ' | ' + entry['reason'] + ' |')
    (folder / 'summary.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps({k: result[k] for k in ('summary', 'profile_errors', 'scope_error', 'unresolved_context')}, indent=2))


if __name__ == '__main__':
    main()
