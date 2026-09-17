# IntelliDocs frontend

React, Vite, and TypeScript frontend for IntelliDocs. Supabase is used in the
browser only for authentication; document storage, database access, processing,
RAG requests, plan limits, and usage summaries go through FastAPI. The Usage view
shows the signed-in user's current plan and remaining allowances.

## Setup

1. Copy `.env.example` to `.env.local`.
2. Add the Supabase project URL and anon/publishable key.
3. Run `npm install`.
4. Start the backend on port 8000.
5. Run `npm run dev` and open `http://localhost:5173`.

Use `npm test`, `npm run typecheck`, and `npm run build` for verification.
