"""stripe_sandbox_billing

Revision ID: d8be97cc24da
Revises: 10b2af4e40d9
Create Date: 2026-10-04 22:11:31.022390
"""
from typing import Sequence, Union
from alembic import op

revision: str = 'd8be97cc24da'
down_revision: Union[str, None] = '10b2af4e40d9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # These tables are server-only: browser users must use authenticated routes,
    # and a webhook must pass signature verification before any state is written.
    op.execute("""
        CREATE TABLE billing_accounts (
            user_id text PRIMARY KEY REFERENCES user_accounts(user_id),
            customer_id text UNIQUE NOT NULL,
            subscription_id text UNIQUE,
            subscription_status text NOT NULL DEFAULT 'none',
            cancel_at_period_end boolean NOT NULL DEFAULT false,
            checkout_session_id text,
            checkout_url text,
            checkout_expires_at timestamptz,
            updated_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE TABLE billing_periods (
            invoice_id text PRIMARY KEY,
            user_id text NOT NULL REFERENCES billing_accounts(user_id),
            subscription_id text NOT NULL,
            period_start timestamptz NOT NULL,
            period_end timestamptz NOT NULL,
            allowance_myr numeric(20,10) NOT NULL CHECK (allowance_myr > 0),
            usd_to_myr numeric(20,10) NOT NULL CHECK (usd_to_myr > 0),
            budget_usd numeric(20,10) NOT NULL CHECK (budget_usd > 0),
            UNIQUE (subscription_id, period_start),
            CHECK (period_end > period_start)
        );
        CREATE INDEX billing_periods_user_idx ON billing_periods(user_id, period_start DESC);
        CREATE TABLE billing_events (
            event_id text PRIMARY KEY,
            event_type text NOT NULL,
            processed_at timestamptz NOT NULL DEFAULT now()
        );
        ALTER TABLE billing_accounts ENABLE ROW LEVEL SECURITY;
        ALTER TABLE billing_periods ENABLE ROW LEVEL SECURITY;
        ALTER TABLE billing_events ENABLE ROW LEVEL SECURITY;
        REVOKE ALL ON billing_accounts, billing_periods, billing_events FROM PUBLIC, anon, authenticated;
    """)

def downgrade() -> None:
    # Drop children first to respect the account ownership foreign keys.
    op.execute("DROP TABLE billing_events; DROP TABLE billing_periods; DROP TABLE billing_accounts;")
