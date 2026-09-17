"""Record provider-reported AI token usage and estimated costs."""

from alembic import op

revision = "20260917_0003"
down_revision = "20260916_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE ai_usage (
            id uuid PRIMARY KEY,
            user_id text NOT NULL,
            document_id uuid,
            conversation_id uuid,
            activity text NOT NULL,
            model text NOT NULL,
            request_id text,
            response_id text,
            attempt integer NOT NULL DEFAULT 1,
            status text NOT NULL,
            input_tokens bigint,
            cached_input_tokens bigint,
            output_tokens bigint,
            reasoning_tokens bigint,
            total_tokens bigint,
            input_rate_usd numeric(16,8),
            cached_input_rate_usd numeric(16,8),
            output_rate_usd numeric(16,8),
            estimated_cost_usd numeric(20,10),
            error_type text,
            created_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX ai_usage_user_created_idx ON ai_usage (user_id, created_at DESC)")
    op.execute("CREATE INDEX ai_usage_document_idx ON ai_usage (document_id, activity)")
    # Historical IDs deliberately have no cascade: usage survives document deletion.
    # No browser access; backend PostgreSQL credentials perform writes.
    op.execute("ALTER TABLE ai_usage ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.execute("DROP TABLE ai_usage")
