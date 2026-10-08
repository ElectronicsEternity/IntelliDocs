# Answer fallback release — 2026-10-08

Scope: development-plan items 1 (mixed-language fallback) and 6 (missing-answer
handling). No retrieval, ingestion, password, email, billing or retention changes.

`backend/app/rag/generator.py` now uses prompt version
`language-aware-evidence-fallback-v4`. Answers follow an explicitly requested
language, otherwise the question language. Original titles, legal identifiers
and verbatim quotations can remain in their original language. The forced
English abstention was removed. General insufficient-evidence notices are:

- English: "I could not find sufficient information in the attached document(s)
  to answer this question."
- Malay: "Saya tidak menemui maklumat yang mencukupi dalam dokumen yang
  dilampirkan untuk menjawab soalan ini."

Singular/plural and question scope should be adapted. Partial answers retain
supported findings and citations, with limitations only for unanswered parts.
The prompt prohibits asserting document-wide absence from missing retrieved
evidence, claiming an unperformed exhaustive search, or inventing source titles.
No broader-search classifier or full-document search was added.

## Verification

53 focused tests passed across `test_answer_fallback.py`, `test_context_packer.py`,
`test_rag_debug_capture.py`, `test_rag_isolation.py` and
`test_reference_following.py`. The 11 new regressions inspect the actual assembled
request with English/Malay/explicit-language questions, zero/single/multiple
document contexts, partial-answer instructions and prompt-version capture.
Responses are mocked: these verify the prompt contract, not actual model output.
No paid AI requests or customer documents were used. An initial test run had
temporary-directory permission errors; rerunning in an isolated workspace
temporary directory passed. No application change was needed for that issue.

## Deployment

To exclude unrelated uncommitted workspace changes, built a two-file patch
context: `generator.py` and `backend/deploy/answer-fallback.Dockerfile` (copied
into the context as `Dockerfile`). No credentials, documents or logs were uploaded.
The Dockerfile pins the previous deployed image, replaces only the generator
and asserts the prompt version during image build. This is a scoped overlay,
not a full rebuild of every local backend change.

- Base image digest: `sha256:2f8d982a2414021ac49b22939ee2caf196c4abef25211c2c1fa587cc56a4130b`.
- Cloud Build: `8c5be525-1331-4535-803a-de43ccdca68d`, SUCCESS.
- New image: `asia-southeast1-docker.pkg.dev/intellidocs-510804/intellidocs/backend@sha256:d3f72e7bb2a80a275dbdbc8c0789be8639a3e982e74375d16c4510967c558a26`.
- Ready revision: `intellidocs-backend-00005-v6c`, verified serving 100% traffic.
- Compared revision specs in memory: unchanged except image; annotations identical.
- Backend `/health`: 200; unauthenticated `/documents`: 401.

Existing service account, secret references, origins, resources/scaling, private
storage, debug capture and cleanup settings were preserved. Previous revision
`intellidocs-backend-00004-gwd` remains available for rollback. GitHub main receives
only the generator, new tests, scoped Dockerfile and this release note; other
pre-existing local changes remain uncommitted. Git used Windows certificate
trust with certificate verification enabled.

Live Malay/English answer behavior and citation quality still require an
authenticated answer acceptance check. Successful infrastructure checks and
mocked regressions are not proof of model compliance or full production readiness.
