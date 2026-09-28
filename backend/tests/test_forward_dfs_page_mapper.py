from types import SimpleNamespace
from uuid import uuid4

from app.indexing.forward_dfs_page_mapper import ForwardDFSPageMapper
from app.indexing.node_scope_extractor import NodeScopeExtractor
from app.models.document_node import DocumentNode
from app.models.page import Page


class Repository:
    def __init__(self, nodes):
        self.nodes = nodes
    def get_by_document(self, _):
        return self.nodes
    def update_page_range(self, **_):
        pass


def node(identity, title='', identifier='', parent=None, sequence=0):
    return DocumentNode(identity, 'doc', parent, 'SECTION', identifier, title, sequence, 0)


def run(nodes, pages, hints):
    doc = SimpleNamespace(id='doc', pages=pages, total_pages=len(pages))
    result = ForwardDFSPageMapper(Repository(nodes)).map_document(doc, hints)
    return doc, result


def test_first_title_match_not_blocked_by_body_repetition():
    nodes = [node('a', 'Prosecution'), node('b', 'Right of audience', sequence=1)]
    doc, result = run(nodes, [Page(1, 'Prosecution 85. No prosecution allowed. Right of audience 85A. body')], {'a': 1, 'b': 1})
    assert not result['unresolved']
    assert nodes[0].start_character == 0
    scopes = NodeScopeExtractor().extract_node_scopes(doc, nodes)
    assert scopes[0]['end_character'] == nodes[1].start_character


def test_repeated_labels_use_forward_cursor():
    nodes = [node('a', identifier='(2)'), node('b', identifier='(2)', sequence=1)]
    _, result = run(nodes, [Page(1, '(2) first (2) second')], {'a': 1, 'b': 1})
    assert not result['unresolved']
    assert [n.start_character for n in nodes] == [0, 10]


def test_missing_parent_does_not_block_child_search():
    nodes = [node('a', 'Missing'), node('b', identifier='(1)', parent='a')]
    _, result = run(nodes, [Page(1, '(1) body')], {'a': 1, 'b': 1})
    assert len(result['unresolved']) == 1
    assert nodes[1].start_character == 0


def test_only_claimed_page_is_searched():
    nodes = [node('a', 'Alpha')]
    _, result = run(nodes, [Page(1, 'Alpha body'), Page(2, 'Other')], {'a': 2})
    assert result['unresolved']
    assert nodes[0].start_page is None


def test_backward_page_hint_is_rejected():
    nodes = [node('a', 'Alpha'), node('b', 'Beta', sequence=1)]
    _, result = run(nodes, [Page(1, 'Beta'), Page(2, 'Alpha body')], {'a': 2, 'b': 1})
    assert result['unresolved'][0]['reason'] == 'page hint precedes forward cursor'


def test_offsets_preserved_across_whitespace_artifacts():
    assert ForwardDFSPageMapper.first_match('Terms and conditions', Page(2, 'xx T erms\n and conditions')) == (2, 3)


def test_identifier_does_not_match_inside_larger_number():
    assert ForwardDFSPageMapper.first_match('4.', Page(1, '14. then 4. body'), identifier=True) == (1, 9)


def test_subsection_and_sibling_ranges_remain_distinct_from_scopes():
    nodes = [node('p', 'Parent'), node('a', identifier='(1)', parent='p'),
             node('b', identifier='(2)', parent='p', sequence=1), node('q', 'Next', sequence=1)]
    doc, result = run(nodes, [Page(1, 'Parent (1) first'), Page(2, '(2) second Next body')], {'p': 1, 'a': 1, 'b': 2, 'q': 2})
    assert not result['unresolved']
    scopes = NodeScopeExtractor().extract_node_scopes(doc, nodes)
    assert scopes[0]['end_character'] == nodes[1].start_character
    assert nodes[0].end_page == nodes[3].start_page


def test_opening_text_skips_earlier_inline_identifier_reference():
    nodes = [node('a', identifier='(2)')]
    doc = SimpleNamespace(id='doc', pages=[Page(1, 'Subject to subsection (2). (2) Wages for work done on a rest day')], total_pages=1)
    result = ForwardDFSPageMapper(Repository(nodes)).map_document(doc, {'a': 1}, opening_texts={'a':'(2) Wages for work done on a'})
    assert not result['unresolved']
    assert nodes[0].start_character == 27


def test_invalid_opening_text_does_not_fall_back_to_identifier():
    nodes = [node('a', identifier='(2)')]
    doc = SimpleNamespace(id='doc', pages=[Page(1, '(2) Different actual text')], total_pages=1)
    result = ForwardDFSPageMapper(Repository(nodes)).map_document(doc, {'a': 1}, opening_texts={'a':'(2) Invented opening text'})
    assert result['unresolved']
    assert nodes[0].start_character is None


def test_title_and_opening_must_agree_at_same_location():
    nodes = [node('a', 'Wages')]
    doc = SimpleNamespace(id='doc', pages=[Page(1, 'Wages reference. Wages for work done')], total_pages=1)
    result = ForwardDFSPageMapper(Repository(nodes)).map_document(doc, {'a': 1}, opening_texts={'a': 'Different opening'})
    assert result['unresolved'][0]['reason'] == 'title and opening text do not confirm the same location'
    assert nodes[0].start_character is None


def test_repeated_title_uses_first_opening_confirmed_location():
    nodes = [node('a', '(Deleted).', identifier='69C.')]
    text = '69B. (Deleted). 69C. (Deleted).'
    doc = SimpleNamespace(id='doc', pages=[Page(1, text)], total_pages=1)
    result = ForwardDFSPageMapper(Repository(nodes)).map_document(doc, {'a': 1}, opening_texts={'a': '69C. (Deleted).'})
    assert not result['unresolved']
    assert nodes[0].start_character == text.index('69C.')


def test_short_heading_and_long_title_prefix_confirm():
    for title, opening in [('Under Part VIII', 'Under Part VIII'),
                           ('Application of this Part irrespective of wages of employee', 'Application of this Part irrespective of wages')]:
        nodes = [node('a', title)]
        doc = SimpleNamespace(id='doc', pages=[Page(1, title + '\n93. body')], total_pages=1)
        result = ForwardDFSPageMapper(Repository(nodes)).map_document(doc, {'a': 1}, opening_texts={'a': opening})
        assert not result['unresolved']
        assert nodes[0].start_character == 0


def test_identifier_directly_before_title_is_same_opening():
    nodes = [node('a', 'Prosecution', identifier='85.')]
    doc = SimpleNamespace(id='doc', pages=[Page(1, '85. Prosecution')], total_pages=1)
    result = ForwardDFSPageMapper(Repository(nodes)).map_document(doc, {'a': 1}, opening_texts={'a': '85. Prosecution'})
    assert not result['unresolved']
    assert nodes[0].start_character == 0


def test_identifier_must_belong_to_heading_not_elsewhere_on_page():
    nodes = [node('a', 'Prosecution', identifier='85.')]
    doc = SimpleNamespace(id='doc', pages=[Page(1, 'Prosecution\n86. body mentioning 85.')], total_pages=1)
    result = ForwardDFSPageMapper(Repository(nodes)).map_document(doc, {'a': 1}, opening_texts={'a': 'Prosecution'})
    assert result['unresolved'][0]['reason'] == 'identifier does not confirm the title/opening location'
    assert nodes[0].start_character is None


def test_identifier_after_heading_and_before_heading_are_supported():
    for text, identifier, title in [('Prosecution\n85. body', '85.', 'Prosecution'),
                                     ('Earlier body\nPART XIV\nINSPECTION', 'PART XIV', 'INSPECTION')]:
        nodes = [node('a', title, identifier=identifier)]
        doc = SimpleNamespace(id='doc', pages=[Page(1, text)], total_pages=1)
        result = ForwardDFSPageMapper(Repository(nodes)).map_document(doc, {'a': 1}, opening_texts={'a': title})
        assert not result['unresolved']


def test_empty_title_still_checks_identifier_against_opening():
    nodes = [node('a', identifier='(2)')]
    doc = SimpleNamespace(id='doc', pages=[Page(1, '(1) Wages for work')], total_pages=1)
    result = ForwardDFSPageMapper(Repository(nodes)).map_document(doc, {'a': 1}, opening_texts={'a': '(1) Wages for work'})
    assert result['unresolved']


def test_scope_extractor_skips_unmapped_anchor_without_aborting_document():
    first = node('a', 'Alpha')
    missing = node('missing', identifier='93.', sequence=1)
    last = node('b', 'Beta', sequence=2)
    first.start_page = 1
    first.start_character = 0
    last.start_page = 1
    last.start_character = 11
    doc = SimpleNamespace(
        id='doc',
        pages=[Page(1, 'Alpha body Beta body')],
        total_pages=1,
    )

    scopes = NodeScopeExtractor().extract_node_scopes(
        doc,
        [first, missing, last],
    )

    assert [scope['node_id'] for scope in scopes] == ['a', 'b']
    assert scopes[0]['text'] == 'Alpha body '


def test_part_title_repetition_does_not_steal_section_heading():
    nodes = [node('a', 'Regulations', identifier='102.')]
    text = 'PART XVIII\nREGULATIONS\nRegulations\n102. body'
    doc = SimpleNamespace(id='doc', pages=[Page(1, text)], total_pages=1)
    result = ForwardDFSPageMapper(Repository(nodes)).map_document(doc, {'a': 1}, opening_texts={'a': 'Regulations'})
    assert not result['unresolved']
    assert nodes[0].start_character == text.index('Regulations')


def test_string_metadata_keys_match_uuid_ids_returned_by_postgres():
    identity = uuid4()
    nodes = [node(identity, 'Alpha')]
    doc = SimpleNamespace(
        id='doc',
        pages=[Page(1, 'Alpha body')],
        total_pages=1,
    )

    result = ForwardDFSPageMapper(Repository(nodes)).map_document(
        doc,
        {str(identity): 1},
        opening_texts={str(identity): 'Alpha'},
    )

    assert not result['unresolved']
    assert nodes[0].start_page == 1
    assert nodes[0].start_character == 0


def test_table_uses_string_keyed_start_page_hint():
    identity = uuid4()
    table = DocumentNode(identity, 'doc', None, 'TABLE', '', '', 0, 0)
    doc = SimpleNamespace(
        id='doc',
        pages=[Page(1, 'body'), Page(2, 'table')],
        total_pages=2,
    )

    result = ForwardDFSPageMapper(Repository([table])).map_document(
        doc,
        {str(identity): 2},
    )

    assert not result['unresolved']
    assert table.start_page == 2
    assert table.end_page == 2
    assert table.start_character is None
