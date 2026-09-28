# Boundary-only mapping lab

The web app continues using `PageMapper`. `CandidatePageMapper` is opt-in and
uses all title/identifier matches with hierarchy-order constraints. Ambiguous
matches remain unresolved except the first titled HEADING directly below the
sole DOCUMENT root, which uses its earliest occurrence. Other headings and
sections do not receive this exception. There is no contents-page heuristic or semantic AI
check. A successful result on one PDF is not proof of general correctness.

## Isolation

- Container: `intellidocs-mapping-lab` (pgvector PostgreSQL 17).
- No published ports; access is through Docker exec only.
- `mapping_baseline`: restored public application tables, read-only by default.
- `mapping_working`: independent clone for boundary updates.
- `.env` and the Supabase database are not changed.
- Supabase-managed auth/storage schemas are excluded. This verifies an
  application-data restore, not a complete Supabase disaster-recovery restore.
- Container data survives stopping/restarting, but not container deletion.
  Preserve the original SQL/PDF backups separately.

## Tools

From the repository root, use the existing virtual environment:

```powershell
.venv/Scripts/python.exe backend/scripts/restore_mapping_lab.py
.venv/Scripts/python.exe backend/scripts/compare_mapping_boundaries.py
```

The restore refuses to overwrite an existing populated lab. It creates tables,
loads public COPY records, then adds foreign keys in one transaction, validating
the self-referential hierarchy without disabling constraints.

The comparison targets only the ready Perintah Gaji Minimum document. It checks
the PDF hash, extracts pages using the existing configured parser, reuses the
saved hierarchy, and changes only `start_page`, `start_character`, and `end_page`
in the working database. No profiling, chat, chunking, or embedding calls run.

The database format is unchanged: start character is stored; exclusive end
character is derived from subsequent sibling/ancestor boundaries, not stored.
The comparator verifies fingerprints of baseline tables, working hierarchy,
and all non-boundary tables. Reports are private Git-ignored files:

- `backups/2026-09-17/boundary-comparison.md`
- `backups/2026-09-17/boundary-comparison.json`

Do not connect the app to this working clone to test chat: once boundaries
change, its copied chunks/embeddings may be stale until separately regenerated.

## First regression result

Perintah Gaji Minimum: 57 nodes, 48 resolved text anchors, 9 structural/table
nodes; all 57 boundary triples identical to the baseline. No unresolved nodes
or existing validator violations. This protects this known-good document; the
failed Akta Kerja PDF has not yet been tested with the new mapper.
