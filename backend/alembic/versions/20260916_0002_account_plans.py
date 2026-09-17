"""Add account plans for configurable trial and Pro limits."""

from alembic import op

revision = "20260916_0002"
down_revision = "20260912_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS user_accounts (
            user_id text PRIMARY KEY,
            plan_code text NOT NULL DEFAULT 'trial',
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT user_accounts_plan_code
                CHECK (plan_code IN ('trial', 'pro'))
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS user_accounts_plan_idx ON user_accounts (plan_code)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS user_accounts")
