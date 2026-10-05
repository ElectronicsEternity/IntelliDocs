# IntelliDocs backend

The backend exposes the existing IntelliDocs parsing, indexing, pgvector retrieval,
and RAG pipeline through FastAPI. Supabase Auth supplies user identity and a private
Supabase Storage bucket stores source PDFs.

## Local setup

1. Copy `.env.example` to `.env` and fill in the required credentials.
2. From the repository root, start PostgreSQL with
   `docker compose --env-file backend/.env up -d postgres`.
3. From `backend/`, install dependencies with `python -m pip install -r requirements.txt`.
4. Apply the schema with `alembic upgrade head`.
5. Start the API with `uvicorn app.main:app --reload`.
6. Run tests with `python -m pytest`.

The health check is available at `GET /health`. All document and chat endpoints
require `Authorization: Bearer <supabase-access-token>`.

## Configurable retention and document deletion

`CHAT_RETENTION_DAYS` and `DEBUG_RETENTION_DAYS` default to 14. Set them in
`backend/.env` and restart the backend to change them; no code edits are needed.
Expiry is per message/capture creation time, not conversation inactivity.
`RETENTION_CLEANUP_ENABLED=true` runs maintenance on startup and every
`RETENTION_CLEANUP_INTERVAL_SECONDS` (default 28800, or eight hours). The backend must be running;
overdue records are removed at its next successful pass. Monitor
`retention_cleanup_failed` logs; a failed database pass does not block file cleanup.
This is not a promise of immediate deletion at exactly the 14-day boundary.

The worker removes expired `messages`, old empty `conversations`, and dated debug
JSON/temporary files. It does not delete `ai_usage`, `usage_records`, allowance
reservations, billing accounts, periods, events, invoices or financial archives.
Ask shows only in-memory current-session messages; navigating away resets them.

Document deletion removes its source PDF, database-linked extraction/search data,
the entire owner/document folder under `DOCUMENT_PROFILES_DIRECTORY`, and that
owner's debugging captures containing the document. The default cache directory
is `backend/documents/Profiles`. Financial/usage history remains. Saved chat
answers remain subject to chat retention rather than document deletion.
Linked folders are rejected. External cleanup finishes before removing the DB
record, so failures can be retried; process/delete operations share an advisory
lock. Do not use playground ingestion scripts concurrently with deletion.

Existing provider copies/backups are governed separately; this worker cannot
erase them. Financial archiving and account-wide deletion are separate work.
Changing retention also requires keeping the published policy accurate.

Test real PostgreSQL SQL without touching user data using
`TEST_RETENTION_DB=1 python -m pytest tests/test_retention.py` (temporary tables,
rolled back). Normal tests use fake DB connections and private temporary folders.

## Account plans and usage

`ai_usage` records each profiling attempt, chunk/node/query embedding response,
and chat response. It stores provider token counts, cached/reasoning breakdowns,
user/document/conversation identifiers, rate snapshots, and estimated USD cost.
Prices are maintained in `app/config.py`. Reasoning tokens are already included
in output tokens and are not billed twice. Missing usage or API errors have a
NULL cost, not zero. Prompts, document text, keys, and error messages are not saved.
Usage history survives document deletion. OpenAI's bill remains authoritative.
SDK retries are disabled: each explicit attempt is separately tracked and reserved.

New authenticated users are assigned the `trial` plan when they first load usage
or perform a limited action. Trial and Pro allowances are configured with the
`TRIAL_*` and `PRO_*` environment variables in `.env.example`. IntelliDocs
enforces document, storage, page-processing, and shared AI-cost allowances.

Stripe sandbox checkout and verified webhooks grant paid subscription periods.
The RM25 allowance and exchange-rate snapshot are fixed for each purchased period;
the default Pro price is RM50/month. FPX passes remain disabled pending activation.

### Allowance reservations

Every budget-enforced provider request reserves its conservative maximum cost in
`ai_usage_reservations` before generation/embedding starts. Per-user PostgreSQL
transaction locks serialize this check with billing changes and other requests.
The lock is committed before network access. Actual usage and hold settlement then
commit together, so holds are not charged on top of actual costs. The displayed
consumption percentage continues to use actual recorded cost, not temporary holds.

Embeddings use local token counts. Text uses a conservative UTF-8 byte estimate;
PDF requests use the provider input-token-count endpoint, including rendered page
images and the JSON schema. All estimates assume uncached input and include the
configured maximum output/reasoning allowance and long-context pricing where
applicable. `CHAT_MAX_OUTPUT_TOKENS` defaults to 128000; existing hierarchy/table
limits are unchanged. This can temporarily reserve much more than the eventual
charge, especially near exhaustion. Insufficient available allowance blocks the
paid call with a retry/narrow-request message, never truncates document evidence.

Explicit provider rejections release their hold. Timeouts, server errors, missing
usage, unknown pricing and failed settlement retain allowance for backend review.
Holds have **no automatic expiry**: elapsed time does not prove a request was unpaid.
Do not manually release an uncertain hold without reconciling the provider outcome.
These private records have RLS enabled and no browser-role grants. Apply migrations
before deploying this backend. Production warning/confirmation UI remains separate.

Run mocked tests with `python -m pytest`. The opt-in PostgreSQL concurrency test is
`TEST_AI_RESERVATIONS_DB=1 python -m pytest tests/test_ai_reservations.py` (set the
environment variable using your shell). It creates unique temporary QA records,
removes only those records, and makes no OpenAI calls.

## Supabase setup

Create a private Storage bucket matching `SUPABASE_STORAGE_BUCKET` (default:
`documents`). Keep `SUPABASE_SERVICE_ROLE_KEY` on the backend only. The backend
uses the service role for storage operations after checking document ownership in
PostgreSQL; never expose that key to the future frontend.

Use the Supabase PostgreSQL connection string for `DATABASE_URL` (including the
required SSL options). For environments without direct IPv6 connectivity, use the
Supabase session pooler connection string.

For defense in depth, add Storage RLS policies that limit authenticated object paths
to `users/{auth.uid()}/...`. The application-generated path is
`users/{user_id}/documents/{document_id}/{filename}`.
