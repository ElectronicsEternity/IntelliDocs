"""Repair cached Akta v4 failures locally, with at most configured paid calls.

No new full-document profiling call, mapping import, chunks or embeddings.
"""
from decimal import Decimal
import hashlib
import json
import re
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from openai import OpenAI
from app.config import settings
from app.constants import DOCUMENT_PROFILER_MODEL
from app.indexing.candidate_page_mapper import CandidatePageMapper
from app.indexing.document_profile_validator import DocumentProfileValidator
from app.indexing.hierarchy_repair import entries, repair_hierarchy, repair_prompt, missing_entries, preserve_supported_titles
from app.ingestion.parser import PDFParser
from app.services.usage.ai_usage import build_record
from compare_mapping_boundaries import fingerprint
from profile_page_experiment import page_hierarchy_errors
from restore_mapping_lab import BACKUP, sql


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, default=str), encoding='utf-8')


def log_usage(usage):
    data = json.dumps(usage, default=str).replace("'", "''")
    columns = ', '.join(usage)
    sql('mapping_working', f"INSERT INTO ai_usage ({columns}) SELECT {columns} FROM json_populate_record(NULL::ai_usage, '{data}'::json) ON CONFLICT (id) DO NOTHING;")


def main(include_missing=False, validate_saved=False):
    source = BACKUP / 'akta-page-profile-experiment-v4/response.json'
    saved = json.loads(source.read_text(encoding='utf-8'))
    if saved['response']['status'] != 'completed':
        raise RuntimeError('Initial response is incomplete')
    tree = json.loads(saved['output_text'])
    previous = json.loads((BACKUP/'akta-page-profile-experiment-v2/hierarchy-with-pages.json').read_text(encoding='utf-8'))
    metadata = saved['metadata']
    pdf = BACKUP / 'pdfs' / metadata['document']
    if hashlib.sha256(pdf.read_bytes()).hexdigest() != metadata['pdf_hash']:
        raise RuntimeError('Original PDF changed')
    doc_id = saved['usage']['document_id']
    owner = saved['usage']['user_id']
    pages = PDFParser(pdf).extract_text(owner, doc_id, pdf.name).pages
    tables = json.loads(sql('mapping_baseline', "SELECT json_agg(table_name) FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE';"))
    baseline = {t:fingerprint('mapping_baseline',t) for t in tables}
    working = {t:fingerprint('mapping_working',t) for t in tables if t != 'ai_usage'}
    folder = BACKUP / ('akta-page-profile-repair-v2' if include_missing else 'akta-page-profile-repair-v1')
    folder.mkdir(exist_ok=True)
    usage_records = []
    reviewed_reference_adjustments = []
    deterministic_restorations = []
    if validate_saved:
        # Review findings are confined to this PDF-specific lab, not the general
        # missing-node algorithm. Preserve original reference files untouched.
        old_report = json.loads((folder/'validation-report.json').read_text(encoding='utf-8'))
        deterministic_restorations=list(old_report.get('deterministic_title_restorations',[]))
        tree = json.loads((folder/'hierarchy-repaired.json').read_text(encoding='utf-8'))
        usage_records = old_report['repair_usage']
        # Page 100 visibly places 90B after the PART XVII body heading.
        for _,parent in entries(previous):
            for child in list(parent.get('children',[])):
                if child.get('identifier')=='90B.' and parent.get('identifier')=='PART XVI':
                    parent['children'].remove(child)
                    target = next(n for _,n in entries(previous) if n.get('identifier')=='PART XVII')
                    target['children'].insert(0,child)
                    reviewed_reference_adjustments.append('90B belongs under PART XVII on page 100; prior reference parent was incorrect')
        # Do not discard a printed title when a repair returns empty title.
        # Restore only an unambiguous prior identifier/title supported on the
        # newly selected page; never invent or fuzzy-match wording.
        for _,node in entries(tree):
            if node['type']=='SECTION' and not node.get('title','').strip():
                matches=[n for _,n in entries(previous) if n['type']=='SECTION' and
                         re.sub(r'\s+','',n.get('identifier','')).lower()==re.sub(r'\s+','',node.get('identifier','')).lower()]
                selected=[p for p in pages if p.page_number==node.get('start_page')]
                if len(matches)==1 and matches[0]['title'] and CandidatePageMapper._matches(matches[0]['title'],selected):
                    node['title']=matches[0]['title']
                    deterministic_restorations.append({'identifier':node['identifier'],'title':node['title'],'page':node['start_page']})
    normalize = lambda text: re.sub(r'[^A-Za-z0-9]','',text).lower()
    parent_key = lambda n:(n['type'],normalize(n.get('identifier','') or n.get('title','')))
    # The four reference tables were visually verified against this exact PDF.
    # This evidence is specific to the Akta lab, not a general table detector.
    verified_tables = {}
    for path,node in entries(previous):
        if node['type']=='TABLE':
            parent = previous
            for index in path[:-1]:
                parent=parent['children'][index]
            verified_tables[parent_key(parent)]=node['start_page']

    def validate(value):
        failures = []
        for path, node in entries(value):
            if node['type']=='TABLE' and include_missing:
                parent=value
                for index in path[:-1]:
                    parent=parent['children'][index]
                if verified_tables.get(parent_key(parent))!=node.get('start_page'):
                    failures.append({'path':path,'errors':['Table start page/parent not supported by visually verified PDF evidence']})
                continue
            anchor = node.get('title','').strip() or node.get('identifier','').strip()
            if node['type'] in ('DOCUMENT','TABLE') or not anchor:
                continue
            page = node.get('start_page')
            selected = [p for p in pages if type(page) is int and p.page_number == page]
            errors = []
            if not selected:
                errors.append('Start page absent or invalid')
            elif not CandidatePageMapper._matches(anchor, selected, identifier=not bool(node.get('title','').strip())):
                errors.append('Exact heading text absent on reported page')
            identifier = node.get('identifier','').strip()
            if selected and identifier and not CandidatePageMapper._matches(identifier, selected, identifier=True):
                errors.append('Printed identifier absent on reported page')
            if selected and node['type']=='SECTION' and identifier and node.get('title','').strip() and not node['title'].lstrip().startswith('('):
                headings = CandidatePageMapper._matches(node['title'],selected)
                numbers = CandidatePageMapper._matches(identifier,selected,identifier=True)
                if headings and numbers and not any(h[1]<n[1] for h in headings for n in numbers):
                    errors.append('Proposed title follows the section identifier; likely body prose, not its heading')
            if errors:
                failures.append({'path':path,'errors':errors})
        if include_missing:
            failures.extend(missing_entries(previous,value))
        return failures

    before = validate(tree)
    if validate_saved:
        before=validate(json.loads(saved['output_text']))

    def request(current, failures, attempt):
        needed = set()
        for failure in failures:
            if failure.get('kind')=='missing':
                node=failure['candidate']
            else:
                node = current
                for index in failure['path']:
                    node = node['children'][index]
            page = node.get('start_page')
            if type(page) is int:
                needed.update(range(max(1,page-1),min(len(pages),page+1)+1))
        evidence = {p.page_number:p.text for p in pages if p.page_number in needed}
        prompt = repair_prompt(current,failures,evidence)
        if attempt > 1:
            prompt += '\nFor section headings, use the printed heading BEFORE its identifier, not opening prose AFTER it. Deletion notices may follow the identifier.\n'
        cache = folder / f'attempt-{attempt}.json'
        guard = folder / f'attempt-{attempt}-started.json'
        identity = {'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest(),
                    'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
                    'model':DOCUMENT_PROFILER_MODEL,'max_output_tokens':6000}
        if cache.exists():
            result = json.loads(cache.read_text(encoding='utf-8'))
            if result['identity'] != identity:
                raise RuntimeError('Cached repair inputs changed; refusing a paid repeat')
            print(f'Reusing repair attempt {attempt}',flush=True)
        else:
            if guard.exists():
                raise RuntimeError('Uncertain earlier attempt; refusing automatic repeat')
            write_json(guard,identity)
            print(f'Sending targeted repair {attempt}/{settings.HIERARCHY_REPAIR_MAX_ATTEMPTS}: {len(failures)} failed entries',flush=True)
            response, error = None,None
            try:
                client = OpenAI(api_key=settings.OPENAI_API_KEY,max_retries=0,timeout=300)
                response = client.responses.create(model=DOCUMENT_PROFILER_MODEL,input=prompt,max_output_tokens=6000)
            except Exception as exc:
                error = exc
            usage = build_record(response,activity='profiling_hierarchy_repair',model=DOCUMENT_PROFILER_MODEL,
                                 user_id=owner,document_id=doc_id,attempt=attempt,error=error)
            result = {'identity':identity,'response':response.model_dump(mode='json') if response else None,
                      'output_text':response.output_text if response else None,'usage':usage}
            write_json(cache,result)
        log_usage(result['usage'])
        usage_records.append(result['usage'])
        if not result['response']:
            raise RuntimeError('Repair API failed; usage saved, no automatic retry')
        if result['response']['status'] != 'completed':
            return {}  # Count incomplete output against the bounded repair limit.
        try:
            return preserve_supported_titles(current,failures,json.loads(result['output_text']),
                lambda title,page:bool(CandidatePageMapper._matches(title,[p for p in pages if p.page_number==page])))
        except (TypeError,json.JSONDecodeError):
            return {}

    repaired,remaining,history = repair_hierarchy(tree,validate,request,0 if validate_saved else settings.HIERARCHY_REPAIR_MAX_ATTEMPTS)
    if validate_saved:
        history=old_report['history']
    schema_errors = list(DocumentProfileValidator().validate(repaired).errors)
    page_errors = page_hierarchy_errors(repaired)
    section_ids = lambda value:{re.sub(r'[^A-Za-z0-9]','',n['identifier']).lower() for _,n in entries(value) if n['type']=='SECTION'}
    missing_sections = sorted(section_ids(previous)-section_ids(repaired))
    table_count = lambda value:sum(n['type']=='TABLE' for _,n in entries(value))
    blockers = []
    if table_count(repaired)<table_count(previous):
        blockers.append(f'Table coverage unresolved: {table_count(previous)} prior nodes, {table_count(repaired)} current nodes; requires source review')
    if missing_sections:
        blockers.append('Missing prior section identifiers: '+', '.join(missing_sections))
    assert all(fingerprint('mapping_baseline',t)==v for t,v in baseline.items()),'Baseline changed'
    assert all(fingerprint('mapping_working',t)==v for t,v in working.items()),'Working records changed'
    initial_cost = Decimal(str(saved['usage']['estimated_cost_usd']))
    costs = [u['estimated_cost_usd'] for u in usage_records]
    repair_cost = sum((Decimal(str(c)) for c in costs if c is not None),Decimal(0))
    report = {'initial_failures':before,'remaining_failures':remaining,'history':history,
              'retry_limit':settings.HIERARCHY_REPAIR_MAX_ATTEMPTS,'schema_errors':schema_errors,
              'page_order_errors':page_errors,'completeness_blockers':blockers,
              'retrieval_checks_passed':not(remaining or schema_errors or page_errors or blockers),
              'repair_usage':usage_records,'initial_cost_usd':initial_cost,'repair_cost_usd':repair_cost,
              'combined_recorded_cost_usd':initial_cost+repair_cost,
              'cost_complete':all(c is not None for c in costs),
              'completeness_scope':'Prior hierarchy candidates under matched parents; not an exhaustive PDF-derived inventory',
              'table_evidence':'Four Akta reference table layouts visually verified on pages 112, 113, 116, 118',
              'reviewed_reference_adjustments':reviewed_reference_adjustments,
              'deterministic_title_restorations':deterministic_restorations,
              'safety':'All baseline and non-ledger working records unchanged. No mapping imported.'}
    write_json(folder/'hierarchy-repaired.json',repaired)
    write_json(folder/'validation-report.json',report)
    print(json.dumps(report,indent=2,default=str),flush=True)


if __name__=='__main__':
    try:
        main(include_missing='--include-missing' in sys.argv,validate_saved='--validate-saved' in sys.argv)
    except Exception as exc:
        print('Repair experiment stopped: '+type(exc).__name__,flush=True)
        raise SystemExit(1)
