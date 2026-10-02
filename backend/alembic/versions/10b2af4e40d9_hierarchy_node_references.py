"""hierarchy node references

Revision ID: 10b2af4e40d9
Revises: 2e9eba218614
Create Date: 2026-10-02 14:40:12.122085
"""
from typing import Sequence, Union
from alembic import op

revision: str = '10b2af4e40d9'
down_revision: Union[str, None] = '2e9eba218614'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # Add metadata on the existing owner-protected table; no new public table
    # or privileged function is needed, and old nodes remain valid with [].
    op.execute("""
        ALTER TABLE document_nodes ADD COLUMN hierarchy_references jsonb
        NOT NULL DEFAULT '[]'::jsonb
        CHECK (jsonb_typeof(hierarchy_references) = 'array')
    """)

def downgrade() -> None:
    # Rollback removes only the newly introduced reference metadata.
    op.drop_column('document_nodes', 'hierarchy_references')
