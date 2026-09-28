"""Correct only the invented Section 67 subsection in a separate offline copy."""
import copy
import hashlib
import json
from contextlib import redirect_stdout
from io import StringIO

from compare_hierarchy_boundaries import BASE, run
from app.ingestion.parser import PDFParser


def walk(node):
    yield node
    for child in node['children']:
        yield from walk(child)


def main():
    source = BASE / 'akta-gpt56-high-full-opening-texts/hierarchy-with-pages.json'
    pdf = BASE / 'pdfs/Akta Kerja 1955 (Akta 265).pdf'
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    original = json.loads(source.read_text(encoding='utf-8'))
    corrected = copy.deepcopy(original)
    sections = [n for n in walk(corrected) if n['type'] == 'SECTION' and n['identifier'] == '67.']
    assert len(sections) == 1
    section = sections[0]
    invented = section['children'][0]
    assert invented['type'] == 'SUBSECTION' and invented['identifier'] == '(1)'
    assert invented['opening_text'] == '(1) In the course of an inspection'
    remaining = section['children'][1:]
    section['children'] = invented['children'] + remaining
    assert invented['children'] and all(n['type'] == 'CLAUSE' for n in invented['children'])
    assert [n['identifier'] for n in remaining] == ['(2)', '(3)', '(4)']
    assert len(list(walk(corrected))) == len(list(walk(original))) - 1
    folder = BASE / 'akta-section67-corrected-boundary-test'
    folder.mkdir(exist_ok=True)
    output = folder / 'hierarchy-corrected.json'
    output.write_text(json.dumps(corrected, indent=2, ensure_ascii=False), encoding='utf-8')
    document = PDFParser(pdf).extract_text('offline', 'offline', pdf.name)
    with redirect_stdout(StringIO()):
        baseline = run(original, document, forward_dfs=True)
        result = run(corrected, document, forward_dfs=True)
    scopes = result['scopes']
    boundary_checks = {
        'all_text_anchors_resolved': result['summary']['unresolved'] == 0,
        'mapping_validator_passed': result['summary']['mapping_valid'],
        'hierarchy_validator_passed': not result['profile_errors'],
        'scope_extraction_completed': result['scope_error'] is None,
        'scopes_have_positive_ranges': all((s['end_page'], s['end_character']) > (s['start_page'], s['start_character']) for s in scopes),
        'adjacent_scopes_have_no_gaps_or_overlaps': all((a['end_page'], a['end_character']) == (b['start_page'], b['start_character']) for a, b in zip(scopes, scopes[1:])),
        'one_scope_per_text_anchor': len(scopes) == result['summary']['text_anchors'],
    }
    assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash
    report = {'original_sha256': source_hash, 'correction': 'Removed invented subsection (1) under Section 67; promoted its clauses in unchanged order.',
              'baseline_summary': baseline['summary'], 'boundary_checks': boundary_checks,
              'limitations': 'Offline text-boundary checks only. Table geometry and semantic accuracy of every anchor are not certified. No API or database operations.',
              **result}
    (folder / 'validation-report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    lines = ['# Corrected Section 67 boundary test', '', report['correction'], '',
             'Original AI JSON preserved unchanged.', '', '| Check | Passed |', '|---|---|']
    lines += [f'| {key} | {value} |' for key, value in boundary_checks.items()]
    lines += ['', f"Mapped anchors: {result['summary']['resolved']}/{result['summary']['text_anchors']}.",
              f"Extracted scopes: {len(scopes)}.", '', report['limitations']]
    (folder / 'summary.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps({'summary': result['summary'], 'boundary_checks': boundary_checks,
                      'scope_error': result['scope_error'], 'profile_errors': result['profile_errors']}, indent=2))


if __name__ == '__main__':
    main()
