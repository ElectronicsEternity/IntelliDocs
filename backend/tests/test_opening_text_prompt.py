from app.indexing.document_profiler import DocumentProfiler
from app.indexing.hierarchy_prompt_rules import OPENING_TEXT_RULES


def test_main_prompt_includes_opening_text_contract():
    prompt = DocumentProfiler._build_prompt(None, 'Sample source', 'English')
    assert OPENING_TEXT_RULES in prompt
    assert '- opening_text' in prompt
    assert 'first seven words' in prompt
    assert 'or the entire heading if shorter' in prompt
    assert '"opening_text": "Under Part VIII"' in prompt
    assert '"identifier": "93."' in prompt
    assert 'short opening_text excerpt required below' in prompt
    assert 'Never introduce numbering or identifiers not printed in the source' in prompt
    assert 'do not create a subsection "(1)"' in prompt
    assert 'directly under Section 67' in prompt
    assert '- start_page' in prompt
    assert 'PAGE_LABEL values are the only valid source for start_page' in prompt
    assert 'page_coverage' in prompt
    assert 'no_new_nodes_start_here' in prompt


def test_opening_text_rules_preserve_short_headings_and_source_text():
    assert 'separately printed section identifiers' in OPENING_TEXT_RULES
    assert 'deletion notices or amendment annotations to reach seven words' in OPENING_TEXT_RULES
    assert 'never' in OPENING_TEXT_RULES.lower()
    assert 'For DOCUMENT and TABLE nodes' in OPENING_TEXT_RULES
    assert 'return null rather than guessing' in OPENING_TEXT_RULES
