"""document routing profiles

Revision ID: 288b641e8060
Revises: 20260917_0003
Create Date: 2026-09-30 12:36:20.090321
"""
from alembic import op

revision = "288b641e8060"
down_revision = "20260917_0003"
branch_labels = None
depends_on = None

def upgrade() -> None:
    # Keep one current routing profile per document. Topics are derived locally
    # from hierarchy titles, so they require no additional model output.
    op.execute("""
        CREATE TABLE document_routing_profiles (
            document_id uuid PRIMARY KEY REFERENCES documents(id) ON DELETE CASCADE,
            user_id text NOT NULL,
            description text NOT NULL,
            description_embedding vector(1536) NOT NULL,
            topics jsonb NOT NULL DEFAULT '[]'::jsonb,
            profile_version integer NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE INDEX document_routing_profiles_user_idx
        ON document_routing_profiles (user_id, profile_version)
    """)

def downgrade() -> None:
    op.execute("DROP TABLE document_routing_profiles")
