# IntelliDocs remaining work

Updated 2026-10-05. This records agreed follow-up work, not authorization to run paid experiments or deploy changes.

## Usage-page presentation — deferred 2026-10-05

- Documents, storage and pages are account/activity statistics, not measures of
  monthly AI allowance consumption. Replace their quota-style progress bars,
  "of limit" totals and "remaining" labels with simple statistics in a future UI
  update. Distinguish currently stored documents/storage from pages processed
  during a stated period; pages are activity, not current stored capacity.
- Keep AI allowance consumption and remaining percentage in the dedicated AI
  usage indicator. Do not infer paid allowance consumption from document count,
  storage size or page count. This presentation change is recorded only, not
  implemented; it does not authorize removal of backend resource safeguards.

## Large-document upload warning — agreed 2026-10-04

- Before paid processing of a PDF with more than 50 pages, show its page count
  and estimated usage as a percentage of the user's total allocated monthly AI
  allowance. Do not display the estimated processing cost in MYR. Also show the
  remaining allowance as a percentage so users can decide whether to proceed
  or choose a smaller document.
- Require user confirmation to proceed. This is a warning, not an automatic
  rejection based on page count; existing allowance checks still apply.
- Clearly label the usage percentage as an estimate, not a guaranteed deduction.
  Page count alone is insufficient: extraction complexity, tables and retries
  affect cost. Agree and validate the estimation method before implementation.
- This item is recorded for future implementation; no upload behaviour or paid
  processing has been changed by recording it.

## Context size decisions — 2026-10-02

- Implemented conservative same-provision text-overlap reuse and shared document,
  hierarchy and printed-reference labels in the answer prompt. Original chunks,
  provision text, table geometry, citations and debug evidence are preserved.
  Retrieval rankings, exact-section bundles and reference-following remain unchanged.
- Local dry runs against four saved requests preserved every provision/table body
  and reduced estimated prompt tokens by 23–35%. No paid answer retest has yet
  validated answer quality with the new compact-context prompt.
- Still to discuss: a configurable production input-token limit, the allowance
  for supplementary semantic evidence, output/reasoning headroom, and user-facing
  behaviour when complete mandatory sections/references exceed that limit.
  Do not silently truncate mandatory evidence. No new size cap or warning has
  been implemented without agreement on these decisions.
- Reconcile the four-question provider cost increase reported as USD 0.56 with
  the application's USD 0.24194936 estimate. The calculator currently does not
  account for cache-write token rates or returned service-tier differences;
  neither has been established as the cause of this discrepancy.

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

8. Pro pricing discussed 2026-10-04: RM50 monthly subscription with RM25 of
   monthly AI-cost allowance, no rollover, and processing blocked once exhausted.
   Stripe-paid periods snapshot the configurable MYR allowance and USD/MYR rate.
   Legacy manually provisioned development Pro accounts still use the old USD
   setting; do not mistake that for the new subscription allowance.
9. Implement proper cost reservations before API calls so a call or concurrent requests cannot overrun the remaining allowance; reconcile reserved amounts with recorded usage.
10. Set up Stripe registration, checkout, webhooks and Pro activation, including subscription cancellation and payment-event verification.
    User supplied Price ID `price_1UMpGtJ2uPtu69mu9AaYMR6r` on 2026-10-04.
    Verify it belongs to the intended sandbox and RM50 MYR monthly recurring
    price using sandbox credentials before integration; it is not yet verified.
    On 2026-10-04 verified the price is active, sandbox-only, MYR 5000 minor units,
    recurring monthly. Added checkout, customer portal, signed/idempotent payment
    reconciliation, private billing tables and renewal-anniversary usage periods.
    Sandbox webhook signing secret and portal are configured. Tax setup remains
    user-managed.
    FPX follow-up agreed: after card-subscription testing, add a separate RM50
    one-month pass with the same allowance and manual renewal; Stripe FPX does
    not support subscription-mode Checkout or automatic recurring payments.
    Implemented locally 2026-10-05: one-off FPX-only Checkout, signed/canonical
    payment confirmation, private pending-order allowance snapshots, duplicate
    protection, calendar-month expiry, no overlapping paid access, and manual
    renewal UI. Unit tests and rollback-only real SQL tests passed. Stripe's
    sandbox currently reports FPX unavailable/off; the feature remains disabled
    pending activation by the user. Actual bank-authorization, failure/cancel,
    and payment-webhook website tests are still required. Existing paid card
    subscription and allowance have not been changed for this integration.
    First sandbox card payment succeeded on 2026-10-04. Recovered its missed
    invoice.paid event through an authenticated Stripe API read after correcting
    an unquoted PowerShell event filter. Verified Pro activation, one paid period
    ending 2026-11-04 and 100% remaining allowance. Checkout also required removing
    payment_method_types for the current API.
    On 2026-10-05 verified actual signed webhook delivery for cancellation undo:
    the existing account remains active, cancellation notice clears, and its paid
    period/allowance is unchanged. Cancellation date display now recognizes an
    explicit cancel_at equal to the subscription item period end.
    Tested an isolated, clearly named lifecycle QA customer using a Stripe test
    clock: paid renewal creates a fresh allowance with no rollover; failed renewal
    grants no allowance and blocks processing; payment recovery restores active
    status and creates exactly one paid allowance. These were real sandbox API
    events delivered through the listener, not fabricated webhook payloads.
    Exhaustion was tested with simulated usage on the QA account and the actual
    pre-call guard: blocked with HTTP 429, no OpenAI call. QA records are retained
    for audit. Verified 239 backend tests and 23 frontend tests pass. Full website
    presentation of renewal/failure/recovery remains a separate manual UI check;
    sandbox success does not constitute live-production readiness.
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
