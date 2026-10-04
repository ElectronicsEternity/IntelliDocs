"""fpx_month_pass

Revision ID: 975814079bd2
Revises: d8be97cc24da
Create Date: 2026-10-05 00:46:09.893286
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '975814079bd2'
down_revision: Union[str, None] = 'd8be97cc24da'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # Keep one-off bank payments separate from recurring subscription invoices.
    # Pending orders snapshot the purchased allowance before payment completes.
    op.execute("""
        CREATE TABLE billing_fpx_orders (
            checkout_session_id text PRIMARY KEY,
            user_id text NOT NULL REFERENCES billing_accounts(user_id),
            payment_intent_id text UNIQUE,
            status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','paid','review')),
            amount_myr numeric(20,10) NOT NULL CHECK (amount_myr > 0),
            allowance_myr numeric(20,10) NOT NULL CHECK (allowance_myr > 0),
            usd_to_myr numeric(20,10) NOT NULL CHECK (usd_to_myr > 0),
            budget_usd numeric(20,10) NOT NULL CHECK (budget_usd > 0),
            period_start timestamptz,
            period_end timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            CHECK ((status = 'paid' AND period_start IS NOT NULL AND period_end > period_start)
                OR status != 'paid')
        );
        CREATE INDEX billing_fpx_orders_user_idx ON billing_fpx_orders(user_id, period_start DESC);
        ALTER TABLE billing_fpx_orders ENABLE ROW LEVEL SECURITY;
        REVOKE ALL ON billing_fpx_orders FROM PUBLIC, anon, authenticated;
    """)

def downgrade() -> None:
    op.execute('DROP TABLE billing_fpx_orders')
