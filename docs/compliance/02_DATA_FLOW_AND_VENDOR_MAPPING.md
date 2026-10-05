# Data-flow and vendor mapping

Internal working register, 2026-10-05. Based on source review, not a production traffic trace. UNVERIFIED fields must be completed from dashboard/account evidence, without storing credentials here.

## Application paths

```text
Account: User browser -> Supabase Auth -> authenticated IntelliDocs backend

Ingestion: User -> IntelliDocs backend -> Supabase document storage
           storage -> backend temporary working PDF -> OpenAI extraction APIs
           extraction results -> local caches + PostgreSQL hierarchy/chunks
           document/node/profile text -> OpenAI Embeddings API
           returned vectors -> PostgreSQL vector tables

Question: User -> backend -> OpenAI Embeddings API (question text)
          question vector -> PostgreSQL search (per-user document scope)
          selected evidence + question + instructions -> OpenAI answer API
          answer -> user + conversation storage + optional private debug capture

Billing: User -> Stripe Checkout/portal -> signed webhook -> backend billing records
```

The vector database is the PostgreSQL vector store, not a separate vendor. The current backend DATABASE_URL was checked without exposing credentials and points to Supabase-hosted PostgreSQL (database name postgres). On 2026-10-05 the owner supplied a primary-database dashboard screenshot showing Southeast Asia (Singapore), ap-southeast-1. This records the supplied project's primary-database location; it does not establish every provider processing, backup or subprocessor location, or independently match the screenshot's project identity to the connection.

## Receiver register

| Receiver/service | Country/region | Data received; personal data? | Purpose | Storage/retention | Subprocessors / evidence needed |
| --- | --- | --- | --- | --- | --- |
| IntelliDocs backend and local artifact disk | Development machine; production host/country UNVERIFIED | PDF bytes, extracted text, prompts, answers, identifiers; yes, depending on input | Orchestrate processing and retrieval | Temporary PDF cleanup attempted; extraction caches/checkpoints and debug captures persist; 14-day debug retention agreed, automatic cleanup not yet implemented | Identify production compute/disk, disk encryption, admins, replicas/backups and support access |
| Supabase Auth | Account project region and other processing destinations UNVERIFIED | Email, auth/session information; yes | Sign-in and account recovery | Verify auth/log/session settings and account-deletion behavior | Applicable Supabase entity/DPA/subprocessor list; distinguish primary region from other operations |
| Supabase Storage | Actual project region UNVERIFIED | Uploaded PDF, filenames, owner/document paths; yes if content/metadata identify people | Store originals for processing/download | Application storage removal exists; verify bucket access, versions and object backup arrangements | Confirm storage configuration and any file backup service |
| Supabase-hosted PostgreSQL database/vector store | Primary database: Singapore (ap-southeast-1), owner-supplied dashboard screenshot 2026-10-05; project identity match and other destinations not independently verified | Hierarchy, chunks, document descriptions, embeddings, questions/answers, user IDs, usage/billing metadata; personal data may be present, including vectors linked to content | Persist application data and perform vector/identifier/text search | Document-linked database cascade exists; saved questions/answers: 14 days agreed, cleanup pending; actual backups UNVERIFIED | Complete Supabase contract, backup and subprocessor review; primary region is not all processing locations |
| OpenAI extraction: Responses API | Actual org/project processing/storage arrangement UNVERIFIED | PDF/content and extraction instructions/schema; personal data may be present | Identify hierarchy and tables | Current code has no explicit store=false; review endpoint state, abuse-monitoring and approved account controls | Capture applicable entity, accepted processing terms, subprocessor list and configured destinations |
| OpenAI embedding API | UNVERIFIED account destinations | Question text; chunks/node titles/descriptions for indexing; personal data may be present | Produce question/document search vectors | Provider endpoint retention differs from locally stored embeddings; do not call vectors anonymous by default | Same provider review; ensure actual endpoint controls recorded |
| OpenAI answer: Chat Completions API | UNVERIFIED account destinations | Question, selected document evidence/hierarchy labels, instructions; personal data may be present | Generate grounded answers | Verify endpoint/account retention independently from Responses; private IntelliDocs captures/conversations are separate copies | Same provider review; data-sharing/training settings need account evidence |
| Stripe payments | Account contracting entity/processing destinations UNVERIFIED | Email/customer references, subscription/payment metadata; payment details entered in hosted Checkout; yes | Payments, billing, fraud/compliance and access reconciliation | Provider and local billing records have separate retention; no blanket document-delete purge | Review account-specific agreement, DPA/controller roles and relevant subprocessors |
| Production web host/CDN/email/support/monitoring providers | Not selected/verified | Potential request IPs, account messages, diagnostics; yes | Serve app, send account messages, support/monitoring | UNVERIFIED; register before enabling service | Add a separate row for every provider actually used; avoid sending document bodies to analytics/support by default |
| ChatGPT Sites public marketing/policy site, if used | Not yet deployed | Public policy content; actual visitor/hosting processing to verify | Publish information, not host customer document processing | No customer PDFs, keys or private compliance evidence should be uploaded to the public site | Review Sites before deployment; do not assume it is the application's runtime host |

## Transfer record to complete for each receiver

Record legal entity, service/account identifier (not secrets), receiving countries, any onward recipients, data categories/data subjects, purpose, frequency, transfer condition and supporting assessment, notice/consent version if relevant, contract version/acceptance, retention including exceptions, security controls, review date/owner, and unresolved issues. A provider headquarters country is not evidence of all processing destinations.

For a new vendor or region, update this map, processing terms, transfer assessment and notice before introducing the flow. Reassess when data scope, provider subprocessors or account configuration changes.

## Evidence to collect

Backup update, 2026-10-05: owner reports the Supabase dashboard states the current Free plan does not include project backups and offers Pro with up to seven days of scheduled backups. No upgrade or backup configuration was performed. Manual/off-site backups have not been verified. The provider's published database-backup documentation says Storage API objects are not included; PDFs require separate backup coverage. A seven-day recovery window would not replace the agreed seven-year financial archive or fourteen-day active-record retention.

- Database connection destination and confirmed infrastructure ownership; exclude passwords/connection secrets from screenshots.
- Supabase project region, Auth/Storage configuration, backup plan and administrative access evidence.
- OpenAI account retention/data-sharing/region settings and applicable terms; no zero-retention assumption.
- Stripe account entity, processing terms and actual metadata sent.
- Production hosting/email choices, their locations and subprocessors.

Code evidence: backend/app/database/connection.py; storage/postgres_vector_store.py; services/storage/supabase_storage.py; core/auth.py; indexing/document_profiler.py; ingestion/ai_table_processor.py; rag/embedder.py; rag/generator.py; rag/debug_capture.py; schema migrations.

Sources: [OpenAI data controls](https://developers.openai.com/api/docs/guides/your-data), [Supabase shared responsibility](https://supabase.com/docs/guides/deployment/shared-responsibility-model), [Supabase backups](https://supabase.com/docs/guides/platform/backups), [JPDP transfer guidance](https://www.pdp.gov.my/ppdpv1/wp-content/uploads/2025/08/GP_CBPDT_EN.pdf).
