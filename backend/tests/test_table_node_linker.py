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

    with pytest.raises(ValueError, match='0 structural table owners'):
        TableNodeLinker().link_tables([matrix(112, 113)], [root, schedule])
