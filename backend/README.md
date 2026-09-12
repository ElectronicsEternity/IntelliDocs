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
