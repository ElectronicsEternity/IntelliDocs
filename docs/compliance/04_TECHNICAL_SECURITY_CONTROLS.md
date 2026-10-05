# Technical security controls and verification register

Internal baseline, 2026-10-05. CODE = observed implementation, UNVERIFIED = production evidence needed, GAP = missing/incomplete feature identified. This is not a penetration test, production attestation or assurance that every vulnerability was found. No security controls were changed in this documentation task.

| Control | Current evidence / status | Required verification or remediation |
| --- | --- | --- |
| HTTPS/TLS for browser and APIs | Development uses local HTTP; production ingress UNVERIFIED. Provider SDKs/URLs are not evidence of all deployed paths. | Require HTTPS for public app/webhooks; verify certificates, redirect behavior and outbound validation. Local loopback testing is not a public deployment model. |
| Database transport | CODE: psycopg connection accepts DATABASE_URL or host parameters; reviewed fallback does not enforce a TLS/certificate-verification option | Confirm actual destination and negotiated encryption/certificate checks; set production connection requirements. Do not claim end-to-end DB TLS solely from a hosted provider's name. |
| Encryption at rest | Provider/local disk/backup settings UNVERIFIED | Obtain provider assurance for actual services; verify production disks, local artifact storage, backup encryption and access. Do not claim application-level encryption of all content. |
| Authentication | CODE: Supabase token verification through signature/issuer/audience or Auth-server validation | Test invalid/expired tokens, unauthorized requests, recovery and logout; verify production issuer/keys and session revocation requirements |
| Tenant separation | CODE: ownership-scoped repository access and RLS migration with per-user read policies; application DB may use privileged credentials | Test two separate users across documents/search/vectors/conversations/download/delete/billing. RLS does not remove the need for backend owner checks when credentials bypass it. Verify live migrations, grants, functions and views. |
| Role-based/admin access | User isolation exists; full staff/admin role policy and production access inventory UNVERIFIED | Define least-privilege staff roles, MFA, who can view content and production consoles, revocation and access review. Do not advertise unverified role features. |
| Document permissions | CODE: backend storage paths include owner/document IDs; service retrieves records by owner | Confirm private bucket and no public bypass; test guessed identifiers, unauthorized object access and signed-link scope/expiry if used. A namespaced path alone is not authorization. |
| Secrets/API keys | CODE: settings load backend secrets; Supabase service role used server-side | Verify no secret in frontend bundles/repo/history/logs; deploy secrets manager/restricted environment, rotation and least privilege. Do not put keys in this register. |
| Logging/debug captures | CODE: optional private request JSON can contain complete prompts/evidence/answers | Agreed 14-day retention from creation; automatic expiry and earlier document/account-deletion cleanup remain future development. Restrict filesystem access, prevent web exposure and test cleanup; keep minimal cost records separate. Redact credentials and minimize content in production; private is not automatically encrypted. |
| Data minimization for AI | CODE: answer context removes proven overlaps/repeated labels; selection/reference following can expand input. Extraction can send PDF content. | Test contents sent per stage; avoid unrelated user/document data. Token warnings/caps and mandatory-evidence handling remain a separate improvement; do not silently truncate legally relevant evidence. |
| Document deletion | CODE: storage removal followed by DB deletion with cascades | GAP: local caches/checkpoints/debug content not comprehensively purged; test retries, partial failures and processing races. Keep caches while document exists, then remove them on deletion. |
| Conversation/account closure | Current-session-only display and 14-day saved question/answer retention agreed; not implemented/tested in this task | Define session boundary/expiry, implement cleanup, session/access revocation and explicit subscription handling. Keep minimal usage/cost records independent of chat bodies. Do not interpret subscription cancellation as account deletion. |
| Backups and restore | UNVERIFIED provider plan, retention, object coverage and restores | Confirm DB versus file backup coverage, settings and admins; test recovery and replay deletion records after restores. Never promise immediate deletion from expired/immutable snapshots. |
| Retention limits | Debug logs and saved questions/answers: 14 days agreed; necessary accounting records: statutory seven-year period with archiving; cleanup incomplete | Specify triggers/exceptions, implement/test cleanup and integrity-checked archive/retrieval, assess usage/security records separately, verify backup/provider retention |
| Incidents and vendor notices | No completed incident-response evidence collected | Assign incident owner/contact, detection/containment/notification procedure, vendor notice monitoring and rehearsed escalation |
| Dependency and operational security | Existing application/tests are not an infrastructure audit | Review supported versions/lockfiles, vulnerability handling, deploy access, upload abuse controls, monitoring and environment separation |

## Verification records

Each check needs: control ID, actual environment, date/tester, procedure, expected result, observed result, restricted evidence reference, pass/fail, owner and remediation due date. Use isolated QA accounts and non-sensitive sample documents. Do not run destructive checks against customer data.

Mandatory negative checks include cross-user read/search/download/delete attempts, invalid/expired authentication, public storage bypass attempts, access to debug files from the website, leakage of secrets in client builds/logs, and cleanup after a failed or interrupted deletion.

## Priority launch gaps

1. Verify deployment TLS, at-rest protection, private storage, account/role access and tenant-isolation tests.
2. Complete deletion coverage and decide/implement debugging and conversation lifetimes.
3. Verify backup coverage/expiry and restore handling, provider contracts/regions and actual AI-retention settings.
4. Establish operational incident response and a monitored privacy/support contact.

Code anchors: backend/app/core/auth.py; main.py; database/connection.py; services/documents/service.py and repository.py; services/storage/supabase_storage.py; rag/context_packer.py and debug_capture.py; indexing/embedding_checkpoint_store.py; alembic/versions/2e9eba218614_secure_public_tables_with_rls.py. Code review does not establish dashboard settings or live compliance.

Sources: [Supabase shared-responsibility model](https://supabase.com/docs/guides/deployment/shared-responsibility-model), [Supabase backups](https://supabase.com/docs/guides/platform/backups), [OpenAI data controls](https://developers.openai.com/api/docs/guides/your-data), [JPDP personal-data principles](https://www.pdp.gov.my/ppdpv1/en/principles-of-personal-data-protection/).
