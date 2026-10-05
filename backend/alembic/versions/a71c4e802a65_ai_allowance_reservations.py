"""Reserve allowance before provider calls without holding a network transaction."""
from alembic import op

revision = "a71c4e802a65"
down_revision = "975814079bd2"
branch_labels = None
depends_on = None


def upgrade():
    # Holds are private accounting records, not additional charges to the user.
    op.execute("""
        CREATE TABLE ai_usage_reservations (
            id uuid PRIMARY KEY,
            user_id text NOT NULL,
            period_start timestamptz NOT NULL,
            period_end timestamptz NOT NULL,
            reserved_usd numeric(20,10) NOT NULL CHECK (reserved_usd >= 0),
            state text NOT NULL DEFAULT 'held'
                CHECK (state IN ('held', 'settled', 'released', 'uncertain')),
            usage_id uuid UNIQUE REFERENCES ai_usage(id),
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CHECK (period_end > period_start)
        );
        CREATE INDEX ai_usage_reservations_open_idx
            ON ai_usage_reservations(user_id, period_start, period_end)
            WHERE state IN ('held', 'uncertain');
        ALTER TABLE ai_usage_reservations ENABLE ROW LEVEL SECURITY;
        REVOKE ALL ON ai_usage_reservations FROM PUBLIC, anon, authenticated;
    """)


def downgrade():
    op.execute("DROP TABLE ai_usage_reservations")
