from types import SimpleNamespace

import pytest

from app.indexing.candidate_page_mapper import CandidatePageMapper
from app.models.document_node import DocumentNode
from app.models.page import Page


class Repository:
    def __init__(self, nodes):
        self.nodes = nodes
        self.saved = {}

    def get_by_document(self, _):
        return self.nodes

    def update_page_range(self, **values):
        self.saved[values['node_id']] = values


def node(key, title='', identifier='', parent=None, sequence=1, kind='SECTION'):
    return DocumentNode(key, 'doc', parent, kind, identifier, title, sequence, 0)


def run(nodes, text):
    repo = Repository(nodes)
    mapper = CandidatePageMapper(repo)
    report = mapper.map_document(SimpleNamespace(id='doc', pages=[Page(1, text)], total_pages=1))
    return repo, report


def test_neighbours_force_later_candidate():
    nodes = [node('a', 'Alpha'), node('b', 'Beta', sequence=2), node('c', 'Gamma', sequence=3)]
    _, report = run(nodes, 'Beta contents Alpha body Beta body Gamma end')
    assert nodes[1].start_character == 25
    assert not report['unresolved']


def test_two_valid_sequences_are_not_guessed():
    nodes = [node('a', 'Alpha'), node('b', 'Beta', sequence=2)]
    repo, report = run(nodes, 'Alpha Beta contents Alpha Beta body')
    assert len(report['unresolved']) == 2
    assert all(n.start_page is None for n in nodes)
    assert repo.saved['a']['start_page'] is None


def test_parent_children_and_same_page_siblings():
    nodes = [node('p', 'Parent'), node('a', identifier='(1)', parent='p'),
             node('b', identifier='(2)', parent='p', sequence=2)]
    _, report = run(nodes, 'Parent (1) first (2) second')
    assert not report['unresolved']
    assert all(n.end_page == 1 for n in nodes)
    assert nodes[0].start_character < nodes[1].start_character < nodes[2].start_character


def test_missing_section_does_not_block_later_section():
    nodes = [node('a', 'Absent'), node('b', 'Beta', sequence=2)]
    _, report = run(nodes, 'Beta body')
    assert nodes[1].start_character == 0
    assert report['unresolved'][0]['reason'] == 'text not found'


def test_duplicate_positions_are_deferred():
    nodes = [node('a', 'Same'), node('b', 'Same', sequence=2), node('c', 'Next', sequence=3)]
    _, report = run(nodes, 'Same Next body')
    assert len(report['unresolved']) == 2
    assert nodes[2].start_character == 5


def test_whitespace_fallback_keeps_original_offsets():
    assert CandidatePageMapper._matches('Terms and conditions', [Page(2, 'xx T erms\n and conditions')]) == [(2, 3)]


def test_identifier_does_not_match_larger_number():
    assert CandidatePageMapper._matches('4.', [Page(1, '14. then 4. actual')], True) == [(1, 9)]


def test_page_hint_restricts_search_to_claimed_page():
    nodes = [node('a', 'Alpha')]
    mapper = CandidatePageMapper(Repository(nodes))
    document = SimpleNamespace(id='doc', pages=[Page(1, 'Alpha contents'), Page(2, 'xx Alpha body')], total_pages=2)
    report = mapper.map_document(document, page_hints={'a': 2})
    assert not report['unresolved']
    assert (nodes[0].start_page, nodes[0].start_character) == (2, 3)


def test_missing_title_on_hint_does_not_search_other_pages():
    nodes = [node('a', 'Alpha')]
    mapper = CandidatePageMapper(Repository(nodes))
    document = SimpleNamespace(id='doc', pages=[Page(1, 'Alpha body'), Page(2, 'Other text')], total_pages=2)
    report = mapper.map_document(document, page_hints={'a': 2})
    assert nodes[0].start_page is None
    assert report['unresolved'][0]['reason'] == 'text not found'


def test_null_hint_is_not_guessed():
    nodes = [node('a', 'Alpha')]
    mapper = CandidatePageMapper(Repository(nodes))
    document = SimpleNamespace(id='doc', pages=[Page(1, 'Alpha body')], total_pages=1)
    report = mapper.map_document(document, page_hints={'a': None})
    assert nodes[0].start_page is None
    assert report['unresolved']


def test_table_inherits_range_without_text_anchor():
    nodes = [node('p', 'Parent'), node('t', 'Table', parent='p', kind='TABLE')]
    _, report = run(nodes, 'Parent body')
    assert not report['unresolved']
    assert nodes[1].start_page == nodes[1].end_page == 1
    assert nodes[1].start_character is None


def test_unresolved_parent_defers_child():
    nodes = [node('p', 'Parent'), node('c', 'Child', parent='p')]
    _, report = run(nodes, 'Parent Parent Child body')
    assert nodes[1].start_page is None
    assert any(r['reason'] == 'parent unresolved' for r in report['unresolved'])


def test_cyclic_hierarchy_is_rejected_before_saving():
    with pytest.raises(ValueError, match='Cyclic'):
        run([node('a', 'Alpha', parent='b'), node('b', 'Beta', parent='a')], 'Alpha Beta')


def test_compact_body_match_is_not_suppressed_by_clean_contents_match():
    matches = CandidatePageMapper._matches('Alpha', [Page(1, 'Alpha contents A lpha body')])
    assert matches == [(1, 0), (1, 15)]


def test_unresolved_mapping_clears_old_database_boundaries():
    n = node('a', 'Missing')
    n.start_page, n.start_character, n.end_page = 10, 99, 12
    repo, _ = run([n], 'Other content')
    assert all(repo.saved['a'][key] is None for key in ('start_page', 'start_character', 'end_page'))


def test_first_document_heading_uses_earliest_match():
    nodes = [node('root', kind='DOCUMENT'),
             node('title', 'Employment Act', parent='root', kind='HEADING'),
             node('section', 'Application', parent='title')]
    _, report = run(nodes, 'Employment Act cover Employment Act Application body')
    assert nodes[1].start_character == 0
    assert nodes[2].start_character == 36
    assert report['document_title_anchor']['id'] == 'title'
    assert not report['unresolved']


def test_document_title_exception_does_not_apply_to_sections():
    nodes = [node('root', kind='DOCUMENT'), node('a', 'Alpha', parent='root')]
    _, report = run(nodes, 'Alpha Alpha body')
    assert nodes[1].start_page is None
    assert report['document_title_anchor'] is None


def test_document_title_exception_does_not_apply_to_later_headings():
    nodes = [node('root', kind='DOCUMENT'),
             node('a', 'Alpha', parent='root', kind='HEADING'),
             node('b', 'Beta', parent='root', kind='HEADING', sequence=2)]
    _, report = run(nodes, 'Alpha Beta Beta body')
    assert nodes[1].start_character == 0
    assert nodes[2].start_page is None


def test_missing_document_title_is_not_invented():
    nodes = [node('root', kind='DOCUMENT'),
             node('title', 'Absent', parent='root', kind='HEADING')]
    _, report = run(nodes, 'Other content')
    assert report['document_title_anchor'] is None
    assert nodes[1].start_page is None
