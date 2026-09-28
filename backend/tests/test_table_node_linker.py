import pytest

from app.indexing.table_node_linker import TableNodeLinker
from app.models.document_node import DocumentNode


def hierarchy_with_tables(*pages):
    root = DocumentNode('root', 'doc', None, 'DOCUMENT', '', '', 0, 0, 1, None, 10)
    tables = [
        DocumentNode(
            f'table-{index}', 'doc', 'root', 'TABLE', '', '', index, 1,
            page, None, page,
        )
        for index, page in enumerate(pages)
    ]
    return [root, *tables], tables


def matrix(*pages):
    return {'page_numbers': list(pages)}


def test_visual_range_refines_hierarchy_table_start_hint():
    nodes, tables = hierarchy_with_tables(3)

    linked = TableNodeLinker().link_tables([matrix(3, 4)], nodes)

    assert linked == ['table-0']
    assert tables[0].start_page == 3
    assert tables[0].end_page == 4


def test_same_page_tables_link_only_when_counts_agree():
    nodes, _tables = hierarchy_with_tables(3, 3)

    linked = TableNodeLinker().link_tables([matrix(3), matrix(3)], nodes)

    assert linked == ['table-0', 'table-1']


def test_same_page_count_mismatch_is_rejected():
    nodes, _tables = hierarchy_with_tables(3, 3)

    with pytest.raises(ValueError, match='matched 2 TABLE nodes and 0 structural'):
        TableNodeLinker().link_tables([matrix(3)], nodes)


def test_exact_schedule_range_can_own_a_physical_table():
    root = DocumentNode('root', 'doc', None, 'DOCUMENT', '', '', 0, 0, 1, None, 127)
    schedule = DocumentNode(
        'schedule', 'doc', 'root', 'SCHEDULE', 'FIRST SCHEDULE',
        '[Subsection 2(1)]', 0, 1, 112, 163, 113,
    )

    linked = TableNodeLinker().link_tables([matrix(112, 113)], [root, schedule])

    assert linked == ['schedule']


def test_structural_owner_requires_an_exact_unique_range():
    root = DocumentNode('root', 'doc', None, 'DOCUMENT', '', '', 0, 0, 1, None, 127)
    schedule = DocumentNode(
        'schedule', 'doc', 'root', 'SCHEDULE', 'FIRST SCHEDULE',
        '', 0, 1, 112, 163, 114,
    )

    nodes = [root, schedule]
    linked = TableNodeLinker().link_tables([matrix(112, 113)], nodes)

    synthetic = next(node for node in nodes if node.id == linked[0])
    assert synthetic.node_type == 'TABLE'
    assert synthetic.parent_id == 'schedule'
    assert (synthetic.start_page, synthetic.end_page) == (112, 113)


def test_front_matter_table_creates_deterministic_root_child():
    root = DocumentNode('root', 'doc', None, 'DOCUMENT', '', '', 0, 0, 1, None, 127)
    section = DocumentNode(
        'section', 'doc', 'root', 'SECTION', '1.', 'Short title',
        0, 1, 15, 0, 17,
    )
    nodes = [root, section]
    table = {
        'table_id': 'publication-history',
        'title': 'Publication and revision history',
        'page_numbers': [2],
    }

    linked = TableNodeLinker().link_tables([table], nodes)

    synthetic = next(node for node in nodes if node.id == linked[0])
    assert synthetic.node_type == 'TABLE'
    assert synthetic.identifier == 'publication-history'
    assert synthetic.title == 'Publication and revision history'
    assert synthetic.parent_id == 'root'
    assert synthetic.depth == 1
    assert synthetic.sequence_no == 0
    assert section.sequence_no == 1
    assert TableNodeLinker().link_tables([table], nodes) == linked


def test_standalone_table_uses_deepest_containing_parent():
    root = DocumentNode('root', 'doc', None, 'DOCUMENT', '', '', 0, 0, 1, None, 20)
    section = DocumentNode(
        'section', 'doc', 'root', 'SECTION', '1.', 'Rates',
        0, 1, 5, 0, 10,
    )
    nodes = [root, section]

    linked = TableNodeLinker().link_tables([
        {
            'table_id': 'rates-table',
            'title': 'Rates by area',
            'page_numbers': [7],
        }
    ], nodes)

    synthetic = next(node for node in nodes if node.id == linked[0])
    assert synthetic.parent_id == 'section'
    assert synthetic.depth == 2
