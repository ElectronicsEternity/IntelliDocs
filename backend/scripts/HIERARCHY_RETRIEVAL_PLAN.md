# Deferred hierarchy retrieval and repair changes

Agreed 2026-09-18. This is a saved design, not implemented functionality.
Compare existing hierarchy outputs against the PDF before integrating these changes.

| Validation | Remarks | Technical implementation |
|---|---|---|
| Page-label integrity | Labels are unique, sequential and cover every extracted page. | Before the API call, compare generated labels with 1 through N, where N is the extracted page count. Reject gaps, duplicates or incorrect order. |
| JSON structure | Required fields, correct types and supported node types. | Parse JSON and validate against a schema defining required fields, types and allowed node types. |
| Hierarchy consistency | Valid parents, depth and sequence; no cycles. Flag suspected duplicates. | Traverse the tree: verify depth increases by one per level and sibling sequence is valid. For ID-based relationships, verify parent references and detect cycles. Flag matching type/identifier/title/page combinations under the same parent. |
| Page validity and exact label references | Use supplied labels; preserve parent/sibling start-page order. Same-page starts are allowed. | Require integer start pages within the supplied labels. Check child.start_page >= parent.start_page and nondecreasing sibling start pages. This alone cannot detect a valid-range number mistakenly copied from printed numbering. |
| Page coverage report | Every page has one of two classifications, consistent with returned nodes. | Require a page_coverage array with one record per label. Group nodes by start page: "new nodes start here" requires at least one node; "no new nodes start here" requires none. |
| API response completion | Detect interrupted or truncated output. | Inspect response status and incomplete details before accepting JSON. Treat unsuccessful or incomplete responses as retrieval failures. |

These checks establish structural consistency and reported coverage, not title accuracy or completeness against the PDF.
Do not add ambiguous-title matching, PDF-based missing-entry detection, or final-page markers to this retrieval-only stage.
Targeted repairs will use the centralized two-retry limit and record token usage/cost for each attempt.

Comparison provenance: existing Akta v4 initial output is GPT-5; the new single-run output is GPT-5.6 Sol with high reasoning. No normal/default GPT-5.6 run exists in this comparison.
