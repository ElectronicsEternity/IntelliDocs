from dataclasses import replace

from app.models.extracted_table import ExtractedTable
from app.ingestion.table_continuation_merger import TableContinuationMerger
from app.ingestion.table_gap_checker import TableGapChecker


def fragment(page, top, bottom):
    return ExtractedTable(page, 1, 500, 1000, (50, top, 450, bottom),
                          [['Employee', 'Rate'], ['A', '100']],
                          [[(50, top, 250, top+20), (250, top, 450, top+20)],
                           [(50, top+20, 250, bottom), (250, top+20, 450, bottom)]])


def word(text, top, bottom, x0=50):
    return {'text': text, 'top': top, 'bottom': bottom, 'x0': x0}


def checker(first=(), second=(), images=()):
    return TableGapChecker({1: {'height': 1000, 'words': list(first), 'images': list(images)},
                            2: {'height': 1000, 'words': list(second), 'images': []}})


def merges(gap, a=None, b=None):
    a = a or fragment(1, 200, 830)
    b = b or fragment(2, 100, 900)
    return TableContinuationMerger()._evaluate_pair(a, b, [a, b], gap)[0]


def test_fallback_requires_context_and_clear_gap():
    assert not merges(None)
    assert merges(checker())
    assert not merges(checker([word('New section heading', 850, 870)]))
    assert not merges(checker(second=[word('Unrelated paragraph', 70, 90)]))
    assert not merges(checker(images=[{'top': 850, 'bottom': 900}]))


def test_page_numbers_ignored_only_in_routine_margins():
    assert merges(checker([word('1', 950, 960)], [word('2', 30, 40)]))
    assert not merges(checker([word('123', 850, 860)]))


def test_fallback_still_requires_matching_headers_alignment_and_page_order():
    assert not merges(checker(), b=replace(fragment(2, 100, 900), rows=[['Different', 'Header'], ['A', '100']]))
    assert not merges(checker(), b=fragment(3, 100, 900))
    assert not merges(checker(), b=fragment(2, 200, 900))
    assert not merges(checker(), b=replace(fragment(2, 100, 900), table_number=2))


def test_existing_bottom_threshold_path_is_unchanged():
    assert merges(None, a=fragment(1, 200, 900))


def test_repeated_routine_header_ignored_but_isolated_heading_blocks():
    pages = {p: {'height': 1000, 'words': [word('Running header', 30, 40)], 'images': []} for p in (1, 2, 3)}
    assert merges(TableGapChecker(pages))
    assert not merges(checker(second=[word('Running header', 30, 40)]))
