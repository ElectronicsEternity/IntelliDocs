# Retention implementation — 2026-10-06

This implementation note supersedes earlier draft statements that local chat/debug
expiry and document-cache removal were unimplemented. It is not a published policy
or proof of deployment.

- Saved chat messages: configurable `CHAT_RETENTION_DAYS`, default 14, from each
  message's creation; empty old conversations are then removed. New activity does
  not extend older messages' retention.
- Debug captures: configurable `DEBUG_RETENTION_DAYS`, default 14, from `started_at`.
  Invalid/abandoned temporary captures use file modification time conservatively.
- The backend runs expiry on startup and every eight hours by default. Downtime or failed
  maintenance delays actual removal; monitor failure logs. Restart after `.env`
  configuration changes. Do not promise deletion at an exact instant.
- Ask shows only the current mounted session, with no history reload. New
  conversation, navigating away, refresh or sign-out clears the UI.
- Document deletion: owner-specific profiles, tables, attempts, embedding
  checkpoints, associated debug captures, source PDF and linked database data are
  removed. Process/delete share an advisory lock; failure keeps the document row
  for retry. Chat answers retain their separate expiry period.
- Never delete usage/cost ledgers, allowance reservations or financial records as
  part of this cleanup. Financial archiving remains pending.
- Provider copies/backups, account-wide deletion, production filesystem protection
  and published policy approval remain separate requirements.

Verification: mocked backend regression suite, frontend tests and type checking;
isolated PostgreSQL temporary-table test exercises the actual expiry SQL and
confirms preserved usage/billing ledger rows. No real document or ledger was deleted
for testing and no paid AI request was made.
