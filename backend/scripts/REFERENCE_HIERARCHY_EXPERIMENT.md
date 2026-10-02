# Local hierarchy-reference experiment

Run `reference_hierarchy_experiment.py --run` once to test the configured
hierarchy model and reasoning level on Akta Kerja physical pages 55-59 and
112-113. The script uses the real hierarchy prompt, with a partial-document
scope note and attached PDF pages for table-layout evidence.

Each node must return a `references` array containing only same-document
targets with `node_type`, `identifier`, and nullable `sub_identifier`.
No reverse references are requested from the model: the experiment resolves
forward references against the returned hierarchy and constructs incoming
lookup locally, including references to children of a requested section.

Private artifacts are saved under `logs/diagnostics/hierarchy_references_v1/`:
the selected PDF, original-page mapping, exact prompt, request-start marker,
raw response and usage, parsed hierarchy, and validation/resolution report.
Cached identical results are reused. SDK retries are disabled. An unmatched
cache or uncertain prior request stops instead of making another paid call.
Absent targets outside the excerpt are reported as unresolved, never invented.

The main acceptance checks are the six explicit references in First Schedule
paragraph 1A's table cell and a reverse link from Section 60A to that table via
60A(3). These checks establish this targeted behavior, not general accuracy
of references throughout all documents.

API usage is recorded through the existing per-user usage tracker. Dollar
cost uses returned token usage and configured model rates; it is not an invoice.
Document records, chunks, embeddings, and live retrieval are not modified.
Production node persistence and one-hop two-way reference following are now
implemented. They do not change similarity scores or the existing unit selection.
Direct linked evidence is added after selection and deduplicated by chunk ID.
Missing/ambiguous targets are retained in diagnostic metadata, not guessed.

`seed_first_schedule_references.py --apply` seeds only the verified First Schedule
and its TABLE in the existing test document, backs up their old metadata, and
replays the Section 60A question using its cached embedding (no API calls).
