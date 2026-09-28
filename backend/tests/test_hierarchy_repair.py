import pytest
from app.indexing.hierarchy_repair import apply_corrections, repair_hierarchy, missing_entries, repair_prompt, preserve_supported_titles


def tree():
    return {'type':'DOCUMENT', 'children':[
        {'type':'SECTION','identifier':'1.','title':'bad','start_page':1,'children':[]},
        {'type':'SECTION','identifier':'2.','title':'sound','start_page':2,'children':[]}]}


def validate(value):
    return [{'path':(0,), 'errors':['title mismatch']}] if value['children'][0]['title'] != 'good' else []


def correction(title='good', path=None):
    return {'corrections':[{'path':[0] if path is None else path,'identifier':'1.','title':title,'start_page':1}]}


def test_success_stops_early_preserves_sound_nodes():
    original = tree()
    calls = []
    def request(value, failures, attempt):
        calls.append(attempt)
        return correction()
    result, failures, history = repair_hierarchy(original, validate, request, 2)
    assert calls == [1] and not failures
    assert result['children'][1] == original['children'][1]
    assert original['children'][0]['title'] == 'bad'


def test_limit_and_zero_attempts():
    calls = []
    def request(value, failures, attempt):
        calls.append(attempt)
        return correction('bad')
    assert repair_hierarchy(tree(), validate, request, 2)[1]
    assert calls == [1,2]
    calls.clear()
    repair_hierarchy(tree(), validate, request, 0)
    assert calls == []


@pytest.mark.parametrize('payload',[correction(path=[1]), {'corrections':[]},
    {'corrections':correction()['corrections'] * 2}, {'corrections':[{'path':[0],'title':'good'}]}])
def test_rejects_unrequested_missing_duplicate_or_structural_edits(payload):
    with pytest.raises(ValueError):
        apply_corrections(tree(), validate(tree()), payload)


def missing_fixture():
    original=tree()
    reference=tree()
    reference['children'][0]['children']=[{'type':'TABLE','identifier':'','title':'','start_page':1,'children':[]}]
    return reference,original,missing_entries(reference,original)


def test_missing_table_sent_and_inserted_under_requested_parent():
    reference,original,failures=missing_fixture()
    prompt=repair_prompt(original,failures,{1:'column A column B'})
    assert 'candidate_id' in prompt and 'TABLE' in prompt
    payload={'corrections':[], 'insertions':[{'candidate_id':failures[0]['candidate_id'],
        'node':reference['children'][0]['children'][0]}]}
    merged=apply_corrections(original,failures,payload)
    assert not missing_entries(reference,merged)
    assert merged['children'][1]==original['children'][1]
    assert original['children'][0]['children']==[]


def test_unverified_candidate_remains_missing_and_consumes_retry_limit():
    reference,original,failures=missing_fixture()
    calls=[]
    def request(current,failed,attempt):
        calls.append(attempt)
        return {'corrections':[], 'insertions':[{'candidate_id':failed[0]['candidate_id'],'node':None}]}
    result,remaining,history=repair_hierarchy(original,lambda t:missing_entries(reference,t),request,2)
    assert calls==[1,2] and len(remaining)==1


def test_unrequested_insertions_and_wrong_types_rejected():
    reference,original,failures=missing_fixture()
    for key,node in [('unknown',reference['children'][0]['children'][0]),
        (failures[0]['candidate_id'],{'type':'SECTION','identifier':'3','title':'','start_page':1,'children':[]})]:
        with pytest.raises(ValueError):
            apply_corrections(original,failures,{'corrections':[], 'insertions':[{'candidate_id':key,'node':node}]})


def test_empty_repair_title_preserves_source_supported_heading_only():
    payload=correction('')
    restored=preserve_supported_titles(tree(),validate(tree()),payload,lambda title,page:True)
    assert restored['corrections'][0]['title']=='bad'
    assert payload['corrections'][0]['title']==''
    unsupported=preserve_supported_titles(tree(),validate(tree()),payload,lambda title,page:False)
    assert unsupported['corrections'][0]['title']==''
