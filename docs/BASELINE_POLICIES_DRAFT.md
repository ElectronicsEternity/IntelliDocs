# IntelliDocs policy baseline and launch gate

Prepared 2026-10-05. INTERNAL DRAFT: not published, not an approved customer contract or legal-compliance certification. Proposed controls below are not claims of implemented features. Malaysian launch baseline; reassess before serving other jurisdictions.

Owner discussion update: overseas-processing work is parked for later discussion, not waived as a launch obligation. Document caches remain while their document is maintained and should be removed when deleted. Debugging logs: 14 days from creation. Ask display: current chat session only. Saved questions/answers: 14 days. Necessary accounting records: statutory seven-year period with periodic secure archiving. Implementation is deferred; session boundary/message expiry and archive mechanics need specification. Do not publish an automatic-expiry promise until implemented and tested. Subscription/cancellation/refund text is drafted separately in SUBSCRIPTION_CANCELLATION_REFUND_DRAFT.md.

## Decisions required before publication

- Business/contact details supplied by owner: PRANOVA SOLUTIONS, sole proprietorship, registration 202603163451 (AS0517057-A); No 26 Jln SG 9/33, Taman Sri Gombak, 68100 Batu Caves, Selangor, Malaysia; hello.intellidocs@gmail.com for support/privacy. Inbox operation has not been tested in this documentation task.
- Approved public website URL and effective date/version.
- Refund policy, including failed delivery, duplicate charges and mandatory consumer rights. Do not invent a blanket no-refund rule.
- Actual hosting/provider regions, contractual safeguards and appropriate basis for overseas personal-data transfers.
- Retention periods, account-closure procedure, backup expiry and incident-response owner.
- Bahasa Malaysia and English privacy notices, checked for consistent meaning.

## Minimum launch gate

1. Privacy: map collected data, purposes, disclosures and rights; give an accurate notice and establish an appropriate processing basis, including special handling where sensitive personal data is involved. Assess whether IntelliDocs is controller or processor for each activity; a customer's permission checkbox is not proof that all uploaded third-party data may lawfully be processed.
2. Security and retention: verify cross-user access isolation, restricted administrative access, HTTPS, protected secrets, limited content logging, deletion and restore procedures. Do not retain personal data indefinitely simply because storage is available.
3. Overseas processing: identify actual destinations and document the applicable section 129 transfer condition and safeguards. Provider names alone are insufficient.
4. Customer/billing disclosures: identify the supplier and support contact; describe the product, full price, renewal, allowance, cancellation and approved refund arrangements clearly before payment. Complete applicable Malaysian online-consumer disclosures and tax obligations before accepting live payments.
5. Incident handling: establish detection, containment, evidence preservation, assessment and notification responsibilities under applicable breach-notification rules. Assess registration and DPO obligations against the actual business/activity; do not assume every small SaaS needs registration or a DPO, or that it is exempt.
6. Stripe readiness: approved public policies, verified account, live product/credentials/webhook, production mode support and end-to-end billing verification. Current sandbox testing is not live readiness.

Legal obligations, Stripe requirements and our technical launch safeguards are different categories. This list is a launch checklist, not an exhaustive legal opinion. Requirements triggered by the business model must be resolved before launch, even if broader improvements are delivered progressively.

## Proposed privacy notice text — owner approval required

IntelliDocs is operated by PRANOVA SOLUTIONS (sole proprietorship), registration 202603163451 (AS0517057-A), contactable at No 26 Jln SG 9/33, Taman Sri Gombak, 68100 Batu Caves, Selangor, Malaysia, and hello.intellidocs@gmail.com.

We process account/contact information, documents and their extracted content, document search data, questions and answers, subscription/payment references, usage records and operational information to provide and secure the service, manage billing and investigate faults. Required account/payment information enables the corresponding service; failure to provide it may prevent access or payment. Optional information and available choices must be identified in the final notice.

Relevant information is processed by service providers including Supabase for application data/authentication/storage, OpenAI for AI processing, and Stripe for payments. The final notice must list actual additional hosting/email providers, disclosure categories, processing destinations and purposes. Stripe handles card entry; verify the deployed integration before making statements about what payment details IntelliDocs itself stores.

During development, private debugging records can contain questions, document excerpts, AI instructions and answers. Production logging must be minimized and have an approved retention period. Do not claim that no staff can access customer information or that all data is immediately deleted.

Access, correction and applicable consent/processing-choice requests may be sent to hello.intellidocs@gmail.com, with proportionate identity verification. The final notice must describe the applicable rights, choices, request procedure and any lawful exceptions, including account closure and deletion arrangements.

Uploaded documents and derived content are retained to provide the service, subject to the approved retention schedule and deletion requests. Certain payment, security or dispute records may be retained where justified or legally required. Backup expiry and provider retention are separate from deletion in active IntelliDocs systems. Insert approved periods only after verifying the implementation.

OpenAI states API data is not used for model training by default unless opted in. Provider retention is nevertheless endpoint/configuration dependent; this is not a zero-retention guarantee. Current code does not explicitly disable Responses application-state storage. Review provider controls and disclose the actual arrangement before launch.

## Proposed service and billing terms — owner approval required

- IntelliDocs supports document ingestion, search and AI-assisted answers. Answers may be incomplete or incorrect; users should verify them against original sources. The service is not a substitute for professional legal or other regulated advice. This does not remove statutory consumer rights or excuse misleading service claims.
- Users retain their rights in uploaded content and must have authority to upload and process it. Any service license should be limited to operating, securing and supporting the service, not unrestricted reuse of confidential documents.
- IntelliDocs Pro currently has an agreed base price of RM50 per month. State the final tax-inclusive/exclusive total clearly before checkout after the owner resolves tax treatment.
- Card subscriptions renew monthly until cancelled. Cancellation normally stops future renewal while paid access continues to the displayed period end, subject to the final approved terms and billing implementation.
- The monthly AI allowance is shared across document processing and questions, tracked using internally calculated processing costs. Unused allowance does not roll over. Processing is blocked when the allowance is insufficient. Describe material changes to allowance/model pricing transparently; do not market this as RM50 of AI credit or unlimited processing.
- Publish the approved refund/contact procedure before live payment. Refund and cancellation are not interchangeable; cancelling a subscription is not automatically deleting the account or its documents.
- No live bank-payment availability should be advertised until enabled and tested. Cards are the initial launch method.
- Define permitted use, suspension grounds, dispute/contact procedure, changes to terms and lawful liability limits in the final contract. Avoid blanket waivers or guarantees of absolute accuracy/security.

## Deletion and retention design — not yet implemented

| Data | Current observation | Required design / proposed baseline |
| --- | --- | --- |
| Uploaded PDF and database document content | DocumentService.delete removes the storage object then the document row; linked hierarchy/chunks/embeddings/profiles use cascading deletion. | Test end-to-end deletion, failures and processing races. Mark deletion, stop new work, remove all artifacts, retry failures and verify completion. |
| Local hierarchy/table caches and embedding checkpoints | Stored under backend/documents/Profiles; not removed by document deletion. | Purge all owner/document caches and attempts on deletion, including the four table JSON files and manifests. Retain caches while an active document needs them under an approved schedule. |
| Saved request/answer debugging JSON | Private logs/rag_debug files; no automatic expiry verified. | Agreed 14 days from creation; configurable automatic cleanup, restricted access and earlier document/account-deletion cleanup need implementation and testing. Minimal usage/cost records remain separate. This is an owner-selected period, not a general statutory period. |
| Temporary processing PDF | Processing finally block attempts to remove its temporary file. | Verify abnormal termination and sweep orphaned temporary files after a short approved period; prevent deletion of an active worker's files. |
| Conversations containing excerpts/answers | Document deletion does not automatically delete conversations. | Ask shows current session only; save questions/answers for 14 days with policy disclosure, no individual expiry warning. This supersedes inactivity-based expiry. Define session boundaries/message expiry and implement cleanup before publishing the promise. |
| Account identity and application data | No dedicated account-deletion workflow identified in the reviewed application. | Authenticated account-closure process covering auth, documents, conversations, storage, local artifacts and providers where controllable. Deal with the subscription separately and prevent accidental continued billing. |
| Usage, invoices/payment references and security audit records | Usage history can survive document deletion. | Necessary accounting records: agreed statutory seven-year period and periodic secure archiving, subject to applicable clock/exceptions. Assess minimal AI usage/security records separately. Chat text is not needed for allowance calculation. Do not retain full prompts as financial evidence. |
| Backups and third-party copies | Exact settings/expiry not verified. | Document actual expiry and access restrictions; apply deletion records after restores. Explain provider retention honestly; do not promise immediate erasure everywhere. |

Proposed automatic schedules are not effective policies until approved, configured, monitored and tested. Do not silently delete an active user's documents solely because they cancel Pro. Define inactive-account retention separately.

Deletion jobs should keep a minimal content-free audit: request ID, scope, time, systems completed, retry/failure status and completion time. Cross-document debugging captures need reliable document linkage so targeted cleanup does not miss them. Avoid retaining deleted content in the deletion audit itself.

## Evidence and sources

- Current code: backend/app/services/documents/service.py (delete and temporary-file cleanup); backend/app/services/documents/repository.py; backend/app/services/storage/supabase_storage.py; backend/app/indexing/embedding_checkpoint_store.py; backend/app/rag/debug_capture.py; schema migrations. Observations are code review, not a successful production deletion test.
- [JPDP personal-data principles](https://www.pdp.gov.my/ppdpv1/en/principles-of-personal-data-protection/): notice, security, retention and access/correction baseline.
- [JPDP privacy-notice guide](https://www.pdp.gov.my/ppdpv1/wp-content/uploads/2025/01/A-Quick-Guide-to-PRIVACY-NOTICE.pdf): section 7 notice guidance, including national-language and English versions. Full PDF fetch was unavailable during this review; publication still needs a complete statutory notice check.
- [JPDP overseas-transfer guidance](https://www.pdp.gov.my/ppdpv1/wp-content/uploads/2025/08/GP_CBPDT_EN.pdf): section 129 conditions, written notification and provider/transfer assessment.
- [JPDP breach-notification guidance](https://www.pdp.gov.my/ppdpv1/en/akta/personal-data-protection-guidelines-on-data-breach-notification-dbn/): consult the current criteria and deadlines when preparing the incident procedure; do not assume all incidents have identical notification duties.
- [Stripe website checklist](https://docs.stripe.com/get-started/checklist/website): product, price/contact and policy disclosures.
- [OpenAI data controls](https://developers.openai.com/api/docs/guides/your-data): provider training/retention distinctions and Responses storage controls.

Next: obtain missing business/contact/refund decisions, finish the applicable Malaysian online-commerce/statutory checks, approve retention periods, implement and test the gaps, then prepare complete bilingual public notices and deploy them. This draft alone is not permission to go live.
