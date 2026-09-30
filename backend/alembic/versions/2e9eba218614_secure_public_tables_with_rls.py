"""secure public tables with rls

Revision ID: 2e9eba218614
Revises: 288b641e8060
Create Date: 2026-09-30 12:38:33.426755
"""
from alembic import op

revision = "2e9eba218614"
down_revision = "288b641e8060"
branch_labels = None
depends_on = None

DIRECT_USER_TABLES = (
    "documents",
    "document_analysis",
    "chunks",
    "embeddings",
    "node_embeddings",
    "conversations",
    "messages",
    "usage_records",
    "user_accounts",
    "document_routing_profiles",
)

def upgrade() -> None:
    # Browser users may read only their own rows. All application writes remain
    # server-side, so no authenticated insert/update/delete policies are added.
    for table in DIRECT_USER_TABLES:
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'DROP POLICY IF EXISTS "read_own_rows" ON "{table}"')
        op.execute(f"""
            CREATE POLICY "read_own_rows" ON "{table}"
            FOR SELECT TO authenticated
            USING ((select auth.uid())::text = user_id)
        """)

    # Nodes inherit ownership through their parent document.
    op.execute("ALTER TABLE document_nodes ENABLE ROW LEVEL SECURITY")
    op.execute('DROP POLICY IF EXISTS "read_own_rows" ON document_nodes')
    op.execute("""
        CREATE POLICY "read_own_rows" ON document_nodes
        FOR SELECT TO authenticated
        USING (EXISTS (
            SELECT 1 FROM documents
            WHERE documents.id = document_nodes.document_id
              AND documents.user_id = (select auth.uid())::text
        ))
    """)

    # Migration history and raw AI billing records are backend-only.
    op.execute("ALTER TABLE alembic_version ENABLE ROW LEVEL SECURITY")
    op.execute("REVOKE ALL ON alembic_version FROM anon, authenticated")
    op.execute("REVOKE ALL ON ai_usage FROM anon, authenticated")

def downgrade() -> None:
    op.execute("GRANT SELECT ON alembic_version TO authenticated")
    op.execute("GRANT SELECT ON ai_usage TO authenticated")
    op.execute('DROP POLICY IF EXISTS "read_own_rows" ON document_nodes')
    op.execute("ALTER TABLE document_nodes DISABLE ROW LEVEL SECURITY")
    for table in DIRECT_USER_TABLES:
        op.execute(f'DROP POLICY IF EXISTS "read_own_rows" ON "{table}"')
        op.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')
    op.execute("ALTER TABLE alembic_version DISABLE ROW LEVEL SECURITY")
