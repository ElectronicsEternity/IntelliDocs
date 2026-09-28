from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from profile_page_experiment import compare_pages, flatten_profile, normalize_section_punctuation, page_hierarchy_errors
from app.models.page import Page
from profile_page_experiment import VERBATIM_HEADING_RULES
from profile_page_experiment import FULL_COVERAGE_RULES


def test_coverage_rules_check_every_page_and_preserve_identifiers():
    assert 'without skipping intermediate pages' in FULL_COVERAGE_RULES
    assert 'second coverage review page by page' in FULL_COVERAGE_RULES
    assert 'Preserve all printed identifiers' in FULL_COVERAGE_RULES
    assert 'Ordinary prose' in FULL_COVERAGE_RULES


def test_verbatim_rules_preserve_deletion_notices_and_opening_page():
    assert 'including the amending Act and footnote marker' in VERBATIM_HEADING_RULES
    assert 'singular/plural' in VERBATIM_HEADING_RULES
    assert 'Do not invent a descriptive heading' in VERBATIM_HEADING_RULES
    assert 'Never use the continuation' in VERBATIM_HEADING_RULES


def tree(page=2):
    return {'type': 'DOCUMENT', 'identifier': '', 'title': '', 'start_page': 1,
            'children': [{'type': 'SECTION', 'identifier': '1', 'title': 'Alpha',
                          'start_page': page, 'children': []}]}


def test_page_comparison_matches_and_validates_text():
    old = flatten_profile(tree())
    summary, results, _ = compare_pages(old, flatten_profile(tree()), [Page(1, 'cover'), Page(2, 'Alpha body')])
    assert summary['text_anchor_pages_matching'] == 1
    assert results[1]['anchor_on_predicted_page']


def test_missing_nodes_count_against_coverage():
    new = tree()
    new['children'] = []
    summary, _, _ = compare_pages(flatten_profile(tree()), flatten_profile(new), [Page(1, 'cover'), Page(2, 'Alpha')])
    assert summary['text_anchors_missing_or_unusable'] == 1


def test_invalid_page_not_counted_as_match():
    summary, _, _ = compare_pages(flatten_profile(tree()), flatten_profile(tree(99)), [Page(1, 'cover'), Page(2, 'Alpha')])
    assert summary['text_anchor_pages_matching'] == 0
    assert summary['text_anchors_missing_or_unusable'] == 1


def test_duplicate_paths_not_silently_paired():
    new = tree()
    new['children'] *= 2
    summary, _, _ = compare_pages(flatten_profile(tree()), flatten_profile(new), [Page(1, 'cover'), Page(2, 'Alpha')])
    assert summary['text_anchors_missing_or_unusable'] == 1


def test_same_section_number_under_different_parents_remains_distinct():
    new = tree()
    section = new['children'][0]
    new['children'] = [{'type': 'HEADING', 'identifier': '', 'title': language,
                        'start_page': 1, 'children': [dict(section, start_page=page)]}
                       for language, page in [('Malay', 2), ('English', 3)]]
    summary, _, extras = compare_pages(flatten_profile(new), flatten_profile(new),
        [Page(1, 'Malay English'), Page(2, 'Alpha'), Page(3, 'Alpha')])
    assert summary['text_anchor_pages_matching'] == 4
    assert not extras


def test_section_number_punctuation_is_only_formatting():
    old = flatten_profile(tree())
    new_tree = tree()
    new_tree['children'][0]['identifier'] = '1.'
    new = flatten_profile(new_tree)
    summary, _, _ = compare_pages(normalize_section_punctuation(old),
        normalize_section_punctuation(new), [Page(1, 'cover'), Page(2, 'Alpha')])
    assert summary['text_anchor_pages_matching'] == 1


def test_page_hierarchy_rejects_child_before_parent():
    profile = tree(1)
    profile['start_page'] = 2
    assert len(page_hierarchy_errors(profile)) == 1


def test_page_hierarchy_rejects_backward_siblings():
    profile = tree(3)
    profile['children'].append({**profile['children'][0], 'identifier': '2', 'start_page': 2})
    assert any('previous sibling' in error for error in page_hierarchy_errors(profile))


def test_page_hierarchy_allows_same_page_parent_and_siblings():
    profile = tree(1)
    profile['children'].append({**profile['children'][0], 'identifier': '2', 'start_page': 1})
    assert not page_hierarchy_errors(profile)


def test_page_hierarchy_checks_previous_sibling_descendants():
    profile = tree(2)
    profile['children'][0]['children'] = [{**tree(4)['children'][0], 'type': 'SUBSECTION'}]
    profile['children'].append({**tree(3)['children'][0], 'identifier': '2'})
    assert any('previous sibling subtree' in error for error in page_hierarchy_errors(profile))


def test_page_hierarchy_keeps_known_ancestor_boundary_through_null_parent():
    profile = tree(None)
    profile['start_page'] = 3
    profile['children'][0]['children'] = [{**tree(2)['children'][0], 'type': 'SUBSECTION'}]
    assert any('ancestor page 3' in error for error in page_hierarchy_errors(profile))
