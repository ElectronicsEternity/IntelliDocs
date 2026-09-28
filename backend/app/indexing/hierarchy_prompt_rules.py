"""Shared opening-text instructions for the main document profiler."""
OPENING_TEXT_RULES = '''
OPENING TEXT RULES
Include "opening_text" on every hierarchy node.
1. If the node has a separate printed heading, copy its first seven words,
or the entire heading if shorter. Include identifiers printed as part of that
heading. Do not add nearby body text, separately printed section identifiers,
deletion notices or amendment annotations to reach seven words.
2. If no separate heading exists, copy up to seven words of the actual provision
opening, beginning with its identifier. Select the provision, not an inline reference.
3. Copy verbatim from the claimed start page. Preserve wording, spelling and
punctuation, including trailing dots in identifiers. Only join line wraps and
normalize whitespace. Never paraphrase, summarize, correct, invent, or combine
text from separate locations or pages.
4. "title" follows existing hierarchy rules, except that a separate printed
heading must NOT be combined with a deletion notice. "opening_text" is a short,
directly searchable source excerpt. This explicit rule overrides instructions
that would otherwise combine these separate pieces.
EXAMPLE: SEPARATE HEADING
PDF text:
Under Part VIII
93. (Deleted by Act A1651).
Correct fields:
"identifier": "93.", "title": "Under Part VIII", "opening_text": "Under Part VIII"
Incorrect title: "Under Part VIII (Deleted by Act A1651)."
Do not create a child solely for a deletion notice. When no separate heading
exists, retain the existing title rules for deleted provisions.
EXAMPLE: IDENTIFIER-ONLY SUBSECTION
PDF text: (2) Wages for work done on a rest day, gazetted public holiday...
Correct fields:
"identifier": "(2)", "title": "", "opening_text": "(2) Wages for work done on a"
Do not select an earlier "Subject to subsection (2)" sentence as its opening.
5. For DOCUMENT and TABLE nodes, return "opening_text": null.
Tables use separate geometry processing.
6. If an opening cannot be established, return null rather than guessing.
Preserve all other required fields, including start_page when requested and children.
This short opening excerpt is the ONLY exception to the rule against extracting body text.
'''
