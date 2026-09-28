"""Boundary-only comparison against the private Docker lab; no API calls."""
import hashlib
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.indexing.candidate_page_mapper import CandidatePageMapper
from app.indexing.page_mapping_validator import PageMappingValidator
from app.ingestion.parser import PDFParser
from app.models.document_node import DocumentNode
from restore_mapping_lab import BACKUP, sql


def fingerprint(db, table, hierarchy_only=False):
    expression = "to_jsonb(t) - 'start_page' - 'start_character' - 'end_page'" if hierarchy_only else 'to_jsonb(t)'
    return sql(db, f'''SELECT md5(coalesce(string_agg(v, E'\\n' ORDER BY v), ''))
        FROM (SELECT ({expression})::text v FROM public."{table}" t) s;''')


class LabRepository:
    def __init__(self, nodes):
        self.nodes = nodes
        self.updates = []

    def get_by_document(self, _):
        return self.nodes

    def update_page_range(self, **values):
        self.updates.append(values)


def main(diagnostic=False):
    tables = json.loads(sql('mapping_baseline', '''SELECT json_agg(table_name ORDER BY table_name)
        FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE';'''))
    baseline = {t: fingerprint('mapping_baseline', t) for t in tables}
    untouched = {t: fingerprint('mapping_working', t) for t in tables if t != 'document_nodes'}
    hierarchy = fingerprint('mapping_working', 'document_nodes', True)
    selection = "original_filename = 'Akta Kerja 1955 (Akta 265).pdf'" if diagnostic else "original_filename ILIKE '%Perintah Gaji Minimum%' AND processing_status='ready'"
    documents = json.loads(sql('mapping_working', f'''SELECT json_agg(d) FROM (
        SELECT id, user_id, original_filename, file_hash FROM documents
        WHERE {selection}
    ) d;''') or '[]')
    if len(documents) != 1:
        raise RuntimeError('Expected exactly one selected document.')
    record = documents[0]
    pdf = BACKUP / 'pdfs' / record['original_filename']
    if hashlib.sha256(pdf.read_bytes()).hexdigest() != record['file_hash']:
        raise RuntimeError('PDF differs from the uploaded original.')
    doc_id = record['id']
    # IDs come only from restored database UUID columns, not user SQL input.
    rows = json.loads(sql('mapping_baseline', f'''SELECT json_agg(n ORDER BY depth, sequence_no, id)
        FROM document_nodes n WHERE document_id='{doc_id}'::uuid;'''))
    fields = ('id','document_id','parent_id','node_type','identifier','title','sequence_no','depth',
              'start_page','start_character','end_page')
    nodes = [DocumentNode(**{k: r[k] for k in fields}) for r in rows]
    document = PDFParser(pdf).extract_text(record['user_id'], doc_id, record['original_filename'])
    repo = LabRepository(nodes)
    mapper = CandidatePageMapper(repo)
    resolution = mapper.map_document(document)
    validation = PageMappingValidator().validate(document, nodes)
    validation_counts = {name: len(getattr(validation, name)) for name in validation.__dataclass_fields__}
    validation_details = {name: [{'id': n.id, 'type': n.node_type,
        'identifier': n.identifier, 'title': n.title} for n in getattr(validation, name)]
        for name in validation.__dataclass_fields__}
    changes = []
    old_by_id = {r['id']: r for r in rows}
    for node in nodes:
        old = old_by_id[node.id]
        previous = [old[k] for k in ('start_page','start_character','end_page')]
        current = [node.start_page, node.start_character, node.end_page]
        changes.append({'id': node.id, 'type': node.node_type, 'identifier': node.identifier,
                        'title': node.title, 'old': previous, 'new': current,
                        'changed': previous != current})
    # Changes are confined to the named working database and one document.
    updates = []
    for value in repo.updates:
        numbers = [('NULL' if value[k] is None else str(int(value[k])))
                   for k in ('start_page','start_character','end_page')]
        updates.append(f'''UPDATE document_nodes SET start_page={numbers[0]},
            start_character={numbers[1]}, end_page={numbers[2]}
            WHERE id='{value['node_id']}'::uuid AND document_id='{doc_id}'::uuid;''')
    sql('mapping_working', 'BEGIN;\n' + '\n'.join(updates) + '\nCOMMIT;')
    assert all(fingerprint('mapping_baseline', t) == baseline[t] for t in tables), 'Baseline changed'
    assert all(fingerprint('mapping_working', t) == v for t, v in untouched.items()), 'Non-boundary table changed'
    assert fingerprint('mapping_working', 'document_nodes', True) == hierarchy, 'Hierarchy changed'
    report = {'document': record['original_filename'], 'mode': 'diagnostic' if diagnostic else 'comparison',
              'resolution': resolution, 'total_nodes': len(nodes),
              'validation': validation_counts, 'validation_details': validation_details, 'boundaries': changes,
              'changed': sum(c['changed'] for c in changes),
              'unchanged': sum(not c['changed'] for c in changes),
              'safety': 'Baseline, hierarchy and all non-boundary tables verified unchanged'}
    output_name = 'akta-boundary-diagnostic' if diagnostic else 'boundary-comparison'
    (BACKUP / (output_name + '.json')).write_text(json.dumps(report, indent=2), encoding='utf-8')
    lines = ['# Akta Kerja boundary diagnostic' if diagnostic else '# Boundary comparison', '', record['original_filename'], '',
             'Diagnostic only: historical boundaries from failed processing are not a correctness baseline.' if diagnostic else 'Comparison against the successful baseline.', '',
             f"Changed: {report['changed']}; unchanged: {report['unchanged']}; resolved text anchors: {resolution['resolved']}; unresolved: {len(resolution['unresolved'])}.",
             '', 'Positions are PDF page / zero-based character / end page. An unresolved mapping is not a successful replacement.',
             '', '| Node | New position |' if diagnostic else '| Node | Old position | New position |',
             '|---|---|' if diagnostic else '|---|---|---|']
    for c in changes:
        label = ' '.join(str(c[k] or '') for k in ('type','identifier','title')).replace('|','\\|').replace('\n',' ')
        lines.append(f"| {label} | {c['new']} |" if diagnostic else f"| {label} | {c['old']} | {c['new']} |")
    lines += ['', '## Unresolved sections', '']
    for item in resolution['unresolved']:
        lines.append(f"- {item['identifier'] or ''} {item['title'] or ''}: {item['reason']} ({item['initial_candidates']} original candidates).")
    lines += ['', '## Validation', '', '```json', json.dumps(validation_counts, indent=2), '```', '', report['safety']]
    (BACKUP / (output_name + '.md')).write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('document','changed','unchanged','validation','safety')}, indent=2))
    print(f"Resolved anchors: {resolution['resolved']}; unresolved nodes: {len(resolution['unresolved'])}")


if __name__ == '__main__':
    arguments = argparse.ArgumentParser(description=__doc__)
    arguments.add_argument('--akta-diagnostic', action='store_true',
                           help='Run the failed Akta Kerja PDF as a diagnostic, not a successful-baseline comparison.')
    main(diagnostic=arguments.parse_args().akta_diagnostic)
