"""Offline seven-word excerpt regression using the four cached verified openings."""
import copy
import hashlib
import json
from pathlib import Path

from compare_hierarchy_boundaries import BASE, run
from app.ingestion.parser import PDFParser


def main():
    original_path = BASE / 'akta-gpt56-high-once/hierarchy-with-pages.json'
    excerpt_path = BASE / 'akta-four-opening-texts-gpt56-high/hierarchy-with-four-opening-texts.json'
    reference_path = BASE / 'akta-four-opening-texts-gpt56-high/validation-report.json'
    inputs = [original_path, excerpt_path, reference_path]
    before_hash = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
    original = json.loads(original_path.read_text(encoding='utf-8'))
    seven = copy.deepcopy(json.loads(excerpt_path.read_text(encoding='utf-8')))
    references = json.loads(reference_path.read_text(encoding='utf-8'))['results']
    excerpts = {}
    count = 0
    def shorten(node):
        nonlocal count
        identity = 'node-' + str(count)
        count += 1
        if node.get('opening_text'):
            node['opening_text'] = ' '.join(node['opening_text'].split()[:7])
            excerpts[identity] = node['opening_text']
        for child in node['children']:
            shorten(child)
    shorten(seven)
    assert set(excerpts) == {n['node_id'] for n in references} and len(excerpts) == 4
    document = PDFParser(BASE / 'pdfs/Akta Kerja 1955 (Akta 265).pdf').extract_text('offline', 'offline', 'Akta')
    baseline = run(original, document, forward_dfs=True)
    updated = run(seven, document, forward_dfs=True)
    old = {p['id']: p for p in baseline['positions']}
    new = {p['id']: p for p in updated['positions']}
    verification = [{'node_id': r['node_id'], 'path': r['path'], 'opening_text': excerpts[r['node_id']],
                     'page': new[r['node_id']]['start_page'], 'character': new[r['node_id']]['start_character'],
                     'expected_character': r['expected_character'],
                     'passed': new[r['node_id']]['start_page'] == r['page'] and new[r['node_id']]['start_character'] == r['expected_character']}
                    for r in references]
    other_changes = [{'old': old[k], 'new': new[k]} for k in old if k not in excerpts and old[k] != new[k]]
    assert all(r['passed'] for r in verification)
    assert not other_changes
    assert all(hashlib.sha256(p.read_bytes()).hexdigest() == h for p,h in before_hash.items())
    folder = BASE / 'akta-seven-word-opening-test'
    folder.mkdir(exist_ok=True)
    (folder / 'hierarchy-seven-word-openings.json').write_text(json.dumps(seven, indent=2, ensure_ascii=False), encoding='utf-8')
    report = {'four_node_checks': verification, 'other_mapping_changes': other_changes,
              'other_nodes_unchanged': len(old)-4, 'baseline_summary': baseline['summary'],
              'updated_summary': updated['summary'], 'scope_error': updated['scope_error'],
              'profile_errors': updated['profile_errors'], 'validation': updated['validation'],
              'positions': updated['positions'], 'scopes': updated['scopes'],
              'scope': 'No API/database operations. Exact scope extraction remains gated by all anchors; no bridging unresolved nodes.'}
    (folder / 'validation-report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    lines = ['# Seven-word opening test', '', 'Four verified starts pass; all other node positions and coarse end pages remain unchanged.', '',
             '| Node | Seven-word opening | PDF page | Start character | Passed |', '|---|---|---:|---:|---|']
    for r in verification:
        lines.append(f"| {' > '.join(r['path']).replace('|', '/')} | {r['opening_text']} | {r['page']} | {r['character']} | {r['passed']} |")
    lines += ['', f"Other nodes unchanged: {len(old)-4}.", '', 'Scope extraction: ' + str(updated['scope_error']), '',
              'Six source-backed duplicate groups still fail production profile validation. Live integration and production validators are unchanged.', '',
              'Changing four starts necessarily changes adjacent exact text-scope boundaries once full extraction becomes possible; unchanged other starts/coarse end pages does not mean all final scopes are unchanged.']
    (folder / 'summary.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    print(json.dumps({'four_checks':verification, 'other_nodes_unchanged':len(old)-4,
                      'other_changes':len(other_changes), 'summary':updated['summary'], 'scope_error':updated['scope_error']}, indent=2))


if __name__ == '__main__':
    main()
