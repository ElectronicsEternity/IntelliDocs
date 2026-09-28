from app.indexing.document_profile_validator import DocumentProfileValidator


def duplicate_errors(openings):
    children = [{'type': 'SUBSECTION', 'identifier': '(2)', 'title': '',
                 'opening_text': opening, 'children': []} for opening in openings]
    errors = []
    DocumentProfileValidator()._check_sibling_structure(children, 'SECTION', errors)
    return errors


def test_different_openings_allow_repeated_printed_labels():
    assert not duplicate_errors(['(2) Corporation', '(2) Person'])


def test_same_opening_is_duplicate_even_with_line_wraps():
    assert len(duplicate_errors(['(2) Same content', '(2) Same\ncontent'])) == 1


def test_missing_openings_continue_without_duplicate_error():
    assert not duplicate_errors([None, None, '', '   ', '(2) Existing'])


def test_missing_opening_does_not_hide_later_confirmed_duplicate():
    assert len(duplicate_errors([None, '(2) Same', '(2) Same'])) == 1
