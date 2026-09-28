"""Offline stages 5-7: page-hint anchors, ranges, validators and exact scopes.

Diagnostic conversion preserves invalid profiles to expose downstream failures;
normal importer validation is reported separately, never bypassed in the app.
No API requests, database writes, chunks or embeddings.
"""
import hashlib
import json
from collections import Counter
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import sys
import argparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.models.document_node import DocumentNode
from app.ingestion.parser import PDFParser
from app.indexing.candidate_page_mapper import CandidatePageMapper
from app.indexing.forward_dfs_page_mapper import ForwardDFSPageMapper
from app.indexing.page_mapping_validator import PageMappingValidator
from app.indexing.document_profile_validator import DocumentProfileValidator
from app.indexing.node_scope_extractor import NodeScopeExtractor

BASE = Path(__file__).resolve().parents[2] / 'backups' / '2026-09-17'


class MemoryRepository:
    def __init__(self, nodes):
        self.nodes = nodes

    def get_by_document(self, _):
        return self.nodes

    def update_page_range(self, **_):
        pass


def convert(tree):
    nodes, hints, paths = [], {}, {}

    def visit(raw, parent=None, depth=0, sequence=0, prefix=()):
        identity = 'node-' + str(len(nodes))
        node = DocumentNode(identity, 'offline', parent, raw['type'], raw['identifier'], raw['title'], sequence, depth)
        nodes.append(node)
        hints[identity] = raw.get('start_page')
        paths[identity] = prefix + (f"{node.node_type} {node.identifier} {node.title}".strip(),)
        for i, child in enumerate(raw['children']):
            visit(child, identity, depth + 1, i, paths[identity])
    visit(tree)
    return nodes, hints, paths


def run(tree, document, forward_dfs=False):
    nodes, hints, paths = convert(tree)
    mapper_class = ForwardDFSPageMapper if forward_dfs else CandidatePageMapper
    mapper = mapper_class(MemoryRepository(nodes))
    extra = {}
    if forward_dfs:
        def walk(raw):
            yield raw
            for child in raw['children']:
                yield from walk(child)
        extra['opening_texts'] = {node.id: raw['opening_text'] for node, raw in zip(nodes, walk(tree)) if raw.get('opening_text')}
    resolution = mapper.map_document(document, page_hints=hints, **extra)
    validation = PageMappingValidator().validate(document, nodes, opening_texts=extra.get('opening_texts'))
    details = {field: [{'id': n.id, 'path': paths[n.id]} for n in getattr(validation, field)]
               for field in validation.__dataclass_fields__}
    scopes, scope_error = [], None
    try:
        scopes = NodeScopeExtractor().extract_node_scopes(document, nodes)
    except ValueError as exc:
        scope_error = str(exc)
    anchors = [n for n in nodes if n.node_type != 'TABLE' and (n.title.strip() or n.identifier.strip())]
    common = [n for n in anchors if n.node_type not in ('SUBSECTION', 'CLAUSE')]
    counts = {'total_nodes': len(nodes), 'text_anchors': len(anchors),
              'resolved': resolution['resolved'], 'unresolved': len(resolution['unresolved']),
              'common_anchors': len(common), 'common_resolved': sum(n.start_character is not None for n in common),
              'scope_count': len(scopes), 'mapping_valid': validation.is_valid,
              'reason_counts': dict(Counter(n['reason'] for n in resolution['unresolved'])),
              'validation_counts': {k: len(v) for k, v in details.items()}}
    return {'summary': counts, 'profile_errors': list(DocumentProfileValidator().validate(tree).errors),
            'resolution': resolution, 'validation': details, 'scope_error': scope_error,
            'positions': [{'id': n.id, 'path': paths[n.id], 'hint': hints[n.id], 'start_page': n.start_page,
                           'start_character': n.start_character, 'end_page': n.end_page} for n in nodes],
            'scopes': [{k: v for k, v in scope.items() if k != 'text'} | {'text_length': len(scope['text'])} for scope in scopes]}


def main(forward_dfs=False):
    pdf = BASE / 'pdfs' / 'Akta Kerja 1955 (Akta 265).pdf'
    sources = {'GPT-5 initial v4': BASE / 'akta-page-profile-experiment-v4',
               'GPT-5.6 high initial': BASE / 'akta-gpt56-high-once'}
    hashes = {str(p / 'hierarchy-with-pages.json'): hashlib.sha256((p / 'hierarchy-with-pages.json').read_bytes()).hexdigest() for p in sources.values()}
    document = PDFParser(pdf).extract_text('offline', 'offline', pdf.name)
    results = {}
    for label, folder in sources.items():
        saved = json.loads((folder / 'response.json').read_text(encoding='utf-8'))
        assert hashlib.sha256(pdf.read_bytes()).hexdigest() == saved['metadata']['pdf_hash']
        tree = json.loads((folder / 'hierarchy-with-pages.json').read_text(encoding='utf-8'))
        with redirect_stdout(StringIO()):
            results[label] = run(tree, document, forward_dfs=forward_dfs)
    assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == h for p, h in hashes.items())
    folder = BASE / ('akta-forward-dfs-comparison' if forward_dfs else 'akta-stage5-7-comparison')
    folder.mkdir(exist_ok=True)
    limitations = ('Same strict page-hint candidate mapper and existing validators/scope extractor for both. '
                   'No title edits or identifier fallbacks. Tables retain inherited coarse ranges, not verified geometric boundaries. '
                   'Invalid profile conversion is diagnostic only; production importer remains unchanged. '
                   'Gap/overlap coverage is not certified when full scope extraction fails.')
    if forward_dfs:
        limitations = 'First-match forward DFS; claimed-page-only search after previous anchor; no parent range or ambiguity blocking. ' + limitations.replace('strict page-hint candidate mapper', 'forward DFS mapper')
    (folder / 'comparison.json').write_text(json.dumps({'method': limitations, 'results': results}, indent=2, ensure_ascii=False), encoding='utf-8')
    lines = ['# Stages 5-7 comparison', '', limitations, '',
             '| Output | Resolved text anchors | Common-level resolved | Exact scopes | Mapping valid |', '|---|---:|---:|---:|---|']
    for name, result in results.items():
        s = result['summary']
        lines.append(f"| {name} | {s['resolved']}/{s['text_anchors']} | {s['common_resolved']}/{s['common_anchors']} | {s['scope_count']} | {s['mapping_valid']} |")
    for name, result in results.items():
        lines += ['', '## ' + name, '', 'Scope extraction: ' + (result['scope_error'] or 'passed'), '',
                  '| Unresolved node | Reason |', '|---|---|']
        positions = {p['id']: p for p in result['positions']}
        for entry in result['resolution']['unresolved']:
            label = ' > '.join(positions[entry['id']]['path']).replace('|', '\\|')
            lines.append(f"| {label} | {entry['reason']} |")
    (folder / 'comparison.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps({name: {'summary': r['summary'], 'scope_error': r['scope_error'], 'profile_errors': r['profile_errors']} for name, r in results.items()}, indent=2))


if __name__ == '__main__':
    arguments = argparse.ArgumentParser(description=__doc__)
    arguments.add_argument('--forward-dfs', action='store_true')
    main(forward_dfs=arguments.parse_args().forward_dfs)
