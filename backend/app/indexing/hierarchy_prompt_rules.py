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

# References describe printed links, not inferred legal relationships. Reverse
# lookup is built locally from these forward links rather than invented by GPT.
REFERENCE_RULES = '''
WITHIN-DOCUMENT REFERENCE RULES
Include "references": [] on every hierarchy node, including DOCUMENT and TABLE.
Each reference must contain exactly node_type, identifier, and sub_identifier.
1. Extract only explicit references to provisions of this same document. Do not
include references to other Acts, documents, cases, organizations, or publications.
Do not infer a reference merely because two provisions discuss similar subjects.
2. Attach a reference to the deepest actual hierarchy node whose own text contains
it. A reference in a table cell belongs to that TABLE node if no actual finer
structural node exists. Do not invent table-row nodes or repeat child references
on all ancestors. References in a schedule heading belong to the SCHEDULE node.
3. node_type is the target's top-level structural type, using the allowed node
types. identifier is the target's base identifier, not the source node identifier.
sub_identifier is the complete ordered path below that base, e.g. "(3)(b)".
Use null if the reference names the whole target provision. Preserve letters,
digits and explicit child labels; remove only layout whitespace between the
parts of a citation. Never add missing child labels or invent a destination.
4. Resolve relative wording such as "subsection (1)" or "this section" only when
the current source hierarchy makes the base identifier unambiguous. Otherwise
leave it unrecorded; do not guess. For partial-document tests, references to
explicitly named targets outside the supplied pages may still be recorded, but
do not create those absent targets as hierarchy nodes.
5. Expand an explicitly enumerated list into separate references. Carry forward
a shared section identifier only when the citation grammar unambiguously does
so. Never treat a range of omitted text as evidence of unseen nodes. Deduplicate
identical references within the source node.
6. Copy the reference only where it is printed. Do not invent reverse references
in the target nodes. The application will resolve forward links and build reverse
lookup locally, including subsection references when retrieving their parent.
7. References are structured metadata, an exception to the body-extraction ban.
Do not copy or summarize body text into these three fields.
EXAMPLES (illustrative; extract these only if actually present in the source):
Source table cell: "Subsections 60(3), 60A(3), 60C(2A), 60D(3) and 60D(4)
and section 60J".
The TABLE node receives:
"references": [
  {"node_type":"SECTION","identifier":"60","sub_identifier":"(3)"},
  {"node_type":"SECTION","identifier":"60A","sub_identifier":"(3)"},
  {"node_type":"SECTION","identifier":"60C","sub_identifier":"(2A)"},
  {"node_type":"SECTION","identifier":"60D","sub_identifier":"(3)"},
  {"node_type":"SECTION","identifier":"60D","sub_identifier":"(4)"},
  {"node_type":"SECTION","identifier":"60J","sub_identifier":null}
]
Source clause: "other than an employer referred to in subsubparagraph 4(3)(b)".
That source CLAUSE or SUBSECTION receives:
"references": [{"node_type":"SECTION","identifier":"4","sub_identifier":"(3)(b)"}]
Source schedule heading: "[Subsection 2(1)]".
That SCHEDULE receives:
"references": [{"node_type":"SECTION","identifier":"2","sub_identifier":"(1)"}]
Source: "Part XII" -> {"node_type":"PART","identifier":"XII","sub_identifier":null}.
Source: "section 2 of the Merchant Shipping Ordinance 1952" -> no reference:
the destination is another document. A node with no same-document references
must return an empty array, not null.
'''
