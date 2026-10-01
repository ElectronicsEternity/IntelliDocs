# IntelliDocs remaining work

Updated 2026-10-01. This records agreed follow-up work, not authorization to run paid experiments or deploy changes.

## Retrieval and answer validation

1. Retest document selection with multiple ingested documents, including Minimum Wages Order and Employment Act. Inspect selected documents, selection reasons and retrieved chunks before evaluating answers. The document router and configurable weights are already implemented. On 2026-10-01, corrected scoring to normalize description/topic weights when no meaningful document name is present, and preserved complete exact-reference subtrees through fallback and final merging. Live Section 6 database checks and 159 backend tests passed; website answer retesting remains pending.
2. Rerun all five saved questions below. Verify answers, conditions, citations and displayed sources. Section 6 subtree prioritization and the applicability-clause prompt are already implemented and need regression verification.
   Question answering switched locally to GPT-6.1 Sol Medium on 2026-10-01 with corresponding Standard pricing in usage records. Website retesting remains pending; hierarchy/table extraction models are unchanged.
3. Add the agreed answer guidance: treat exact identifier matches as a strong signal when the question names a provision; prioritize direct textual evidence. Explain match types if supplied to the answer model. Current generator supplies hierarchy, node type and identifier but does not supply retrieval match types.
4. Resolve source-display coverage: ensure users can inspect the evidence used for material claims. Previously five displayed sources did not necessarily represent all ten chunks supplied to the answer model. Discuss the presentation before changing it.
5. Discuss and implement the handling of absence questions such as overtime: distinguish no answer found in retrieved evidence from a verified claim about an entire document, and make document scope clear.
6. Add relevant cross-reference retrieval after an exact section bundle. A retrieval-only replay on 2026-10-01 for the Section 6 applicability question returned all six English Section 6 chunks, but omitted 4(3)(b). The ten-result context instead included 4(3)(a) and three Employment Act chunks. The 4(3)(b) professional-activity/MASCO chunk exists in the database. The original API prompt was not retained; the replay is reproducible evidence, not an archived copy of that request. No answer-generation call was made; one query-embedding call was used.

## Ingestion and model comparison

6. Compare saved GPT-5.6 Sol High hierarchy and table outputs with GPT-6.1 Sol High. Agree the experiment scope first. Compare hierarchy completeness, page starts, usable mappings/boundaries, table cells and semantic associations, elapsed time and recorded API cost. Preserve existing outputs and record model/prompt versions. No API calls are authorized by saving this item.
7. Complete end-to-end regression testing of both legal PDFs, including visual table comparison, retry/cache reuse, interrupted processing, batched embedding progress and routing-profile creation. Successful ingestion and structural checks alone do not confirm full extraction accuracy.

## Allowances, billing and production setup

- Configure private storage and automatic 7/14-day retention for answer debug
  captures before production deployment. Local per-request JSON capture is now
  implemented and enabled under `logs/rag_debug/`; local automatic deletion is deferred.

8. Confirm the provisional USD 20 monthly Pro AI allowance. This is the internal AI usage budget, not an agreed subscription selling price. Consider a stronger answer model for Pro; model choice and pricing remain to be finalized.
9. Implement proper cost reservations before API calls so a call or concurrent requests cannot overrun the remaining allowance; reconcile reserved amounts with recorded usage.
10. Set up Stripe registration, checkout, webhooks and Pro activation, including subscription cancellation and payment-event verification.
11. Configure the production email provider and domain, then complete the deferred email-limit test case 8.

## Saved retrieval regression questions

1. What are the monthly and hourly minimum wage rates under Section 4?
2. What is the daily minimum wage for employees working six, five, or four days per week?
3. Compare the minimum wage rates inside and outside City Council or Municipal Council areas between 1 May 2022 and 31 December 2022.
4. Who does Section 6 apply to, and what minimum wage requirements does it establish?
5. Does this document specify overtime payment rates?

Questions 1, 4 and 5 had identified source/retrieval or answer issues. Questions 2 and 3 are regression checks; do not label them as confirmed failures.

## Already implemented; avoid treating as missing development

- Document selection using title/file name, description similarity and locally derived hierarchy topics, with configurable weights and diagnostics.
- Section subtree prioritization and the controlling applicability-clause answer instruction.
- API usage/cost records and the usage percentage bar.
- Batched embeddings with saved progress.
- Local table response caches and standalone synthetic table nodes.
- Database row-level security. Its ongoing verification belongs in regression testing, not a new implementation item.

The older experimental notes in backend/scripts may describe earlier states. Verify current code before treating those notes as outstanding work.
