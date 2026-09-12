"""Upgrade the existing IntelliDocs schema for multi-user SaaS operation."""

from alembic import op

revision = "20260912_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id uuid PRIMARY KEY, filename text NOT NULL, file_hash text NOT NULL,
            uploaded_at timestamptz NOT NULL DEFAULT now(), owner_id text NOT NULL,
            document_type text, language text, title text
        )
    """)
    op.execute("""
        ALTER TABLE documents
            ADD COLUMN IF NOT EXISTS user_id text,
            ADD COLUMN IF NOT EXISTS original_filename text,
            ADD COLUMN IF NOT EXISTS storage_path text,
            ADD COLUMN IF NOT EXISTS file_size bigint NOT NULL DEFAULT 0,
            ADD COLUMN IF NOT EXISTS file_extension text NOT NULL DEFAULT 'pdf',
            ADD COLUMN IF NOT EXISTS page_count integer,
            ADD COLUMN IF NOT EXISTS processing_status text,
            ADD COLUMN IF NOT EXISTS processing_error text,
            ADD COLUMN IF NOT EXISTS created_at timestamptz,
            ADD COLUMN IF NOT EXISTS updated_at timestamptz
    """)
    op.execute("""
        UPDATE documents d SET
            user_id = COALESCE(d.user_id, d.owner_id),
            original_filename = COALESCE(d.original_filename, d.filename),
            processing_status = COALESCE(d.processing_status, 'uploaded'),
            created_at = COALESCE(d.created_at, d.uploaded_at, now()),
            updated_at = COALESCE(d.updated_at, d.uploaded_at, now())
    """)
    op.execute("""
        ALTER TABLE documents
            ALTER COLUMN user_id SET NOT NULL,
            ALTER COLUMN original_filename SET NOT NULL,
            ALTER COLUMN processing_status SET NOT NULL,
            ALTER COLUMN created_at SET NOT NULL,
            ALTER COLUMN updated_at SET NOT NULL
    """)
    op.execute("CREATE INDEX IF NOT EXISTS documents_user_created_idx ON documents (user_id, created_at DESC)")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS documents_user_hash_idx ON documents (user_id, file_hash)")
    op.execute("""
        DO $$ BEGIN
            ALTER TABLE documents ADD CONSTRAINT documents_public_status
            CHECK (processing_status IN ('uploaded', 'processing', 'ready', 'failed'));
        EXCEPTION WHEN duplicate_object THEN NULL; END $$
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS document_analysis (
            document_id uuid PRIMARY KEY REFERENCES documents(id) ON DELETE CASCADE,
            owner_id text NOT NULL, file_hash text NOT NULL,
            processing_status text NOT NULL, recommended_chunk_size integer,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            page_mapping_version integer, chunking_version integer,
            embedding_version integer
        )
    """)
    op.execute("ALTER TABLE document_analysis ADD COLUMN IF NOT EXISTS user_id text, ADD COLUMN IF NOT EXISTS error_message text")
    op.execute("UPDATE document_analysis SET user_id = COALESCE(user_id, owner_id)")
    op.execute("ALTER TABLE document_analysis ALTER COLUMN user_id SET NOT NULL")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS analysis_user_hash_idx ON document_analysis (user_id, file_hash)")
    op.execute("""
        UPDATE documents d SET processing_status = CASE
            WHEN da.processing_status = 'FAILED' THEN 'failed'
            WHEN da.processing_status = 'INDEXED' THEN 'ready'
            ELSE d.processing_status END
        FROM document_analysis da WHERE da.document_id = d.id
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS document_nodes (
            id uuid PRIMARY KEY, document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            parent_id uuid REFERENCES document_nodes(id) ON DELETE CASCADE,
            node_type text NOT NULL, identifier text, title text,
            sequence_no integer NOT NULL, depth integer NOT NULL,
            start_page integer, start_character integer, end_page integer
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS document_nodes_document_idx ON document_nodes (document_id, depth, sequence_no)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS chunks (
            id uuid PRIMARY KEY, document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            chunk_number integer NOT NULL, page_number integer NOT NULL,
            token_count integer NOT NULL, text text NOT NULL,
            node_id uuid REFERENCES document_nodes(id) ON DELETE CASCADE,
            content_type text NOT NULL, metadata jsonb NOT NULL DEFAULT '{}'::jsonb
        )
    """)
    op.execute("ALTER TABLE chunks ADD COLUMN IF NOT EXISTS user_id text")
    op.execute("UPDATE chunks c SET user_id = d.user_id FROM documents d WHERE d.id = c.document_id AND c.user_id IS NULL")
    op.execute("ALTER TABLE chunks ALTER COLUMN user_id SET NOT NULL")
    op.execute("CREATE INDEX IF NOT EXISTS chunks_user_document_idx ON chunks (user_id, document_id)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS embeddings (
            chunk_id uuid PRIMARY KEY REFERENCES chunks(id) ON DELETE CASCADE,
            embedding vector(1536) NOT NULL
        )
    """)
    op.execute("ALTER TABLE embeddings ADD COLUMN IF NOT EXISTS user_id text")
    op.execute("UPDATE embeddings e SET user_id = c.user_id FROM chunks c WHERE c.id = e.chunk_id AND e.user_id IS NULL")
    op.execute("ALTER TABLE embeddings ALTER COLUMN user_id SET NOT NULL")
    op.execute("CREATE INDEX IF NOT EXISTS embeddings_user_idx ON embeddings (user_id)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS node_embeddings (
            node_id uuid PRIMARY KEY REFERENCES document_nodes(id) ON DELETE CASCADE,
            search_text text NOT NULL, embedding vector(1536) NOT NULL,
            embedding_version integer NOT NULL
        )
    """)
    op.execute("ALTER TABLE node_embeddings ADD COLUMN IF NOT EXISTS user_id text")
    op.execute("""
        UPDATE node_embeddings ne SET user_id = d.user_id
        FROM document_nodes n JOIN documents d ON d.id = n.document_id
        WHERE n.id = ne.node_id AND ne.user_id IS NULL
    """)
    op.execute("ALTER TABLE node_embeddings ALTER COLUMN user_id SET NOT NULL")
    op.execute("CREATE INDEX IF NOT EXISTS node_embeddings_user_idx ON node_embeddings (user_id)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id uuid PRIMARY KEY, user_id text NOT NULL, title text,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS conversations_user_idx ON conversations (user_id, updated_at DESC)")
    op.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id uuid PRIMARY KEY,
            conversation_id uuid NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            user_id text NOT NULL, role text NOT NULL, content text NOT NULL,
            prompt_tokens integer, completion_tokens integer,
            created_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS messages_user_conversation_idx ON messages (user_id, conversation_id, created_at)")
    op.execute("""
        CREATE TABLE IF NOT EXISTS usage_records (
            id bigserial PRIMARY KEY, user_id text NOT NULL, event_type text NOT NULL,
            quantity bigint NOT NULL DEFAULT 1,
            document_id uuid REFERENCES documents(id) ON DELETE SET NULL,
            prompt_tokens integer, completion_tokens integer,
            created_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS usage_user_created_idx ON usage_records (user_id, created_at DESC)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS usage_records")
    op.execute("DROP TABLE IF EXISTS messages")
    op.execute("DROP TABLE IF EXISTS conversations")
    op.execute("DROP INDEX IF EXISTS node_embeddings_user_idx")
    op.execute("ALTER TABLE node_embeddings DROP COLUMN IF EXISTS user_id")
    op.execute("DROP INDEX IF EXISTS embeddings_user_idx")
    op.execute("ALTER TABLE embeddings DROP COLUMN IF EXISTS user_id")
    op.execute("DROP INDEX IF EXISTS chunks_user_document_idx")
    op.execute("ALTER TABLE chunks DROP COLUMN IF EXISTS user_id")
    op.execute("DROP INDEX IF EXISTS analysis_user_hash_idx")
    op.execute("ALTER TABLE document_analysis DROP COLUMN IF EXISTS error_message, DROP COLUMN IF EXISTS user_id")
    op.execute("DROP INDEX IF EXISTS documents_user_hash_idx")
    op.execute("DROP INDEX IF EXISTS documents_user_created_idx")
    op.execute("ALTER TABLE documents DROP CONSTRAINT IF EXISTS documents_public_status")
    op.execute("""
        ALTER TABLE documents
            DROP COLUMN IF EXISTS user_id,
            DROP COLUMN IF EXISTS original_filename,
            DROP COLUMN IF EXISTS storage_path,
            DROP COLUMN IF EXISTS file_size,
            DROP COLUMN IF EXISTS file_extension,
            DROP COLUMN IF EXISTS page_count,
            DROP COLUMN IF EXISTS processing_status,
            DROP COLUMN IF EXISTS processing_error,
            DROP COLUMN IF EXISTS created_at,
            DROP COLUMN IF EXISTS updated_at
    """)
