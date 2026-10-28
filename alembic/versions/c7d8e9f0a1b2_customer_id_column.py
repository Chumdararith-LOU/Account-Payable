"""customer_id column

Revision ID: c7d8e9f0a1b2
Revises: f5289d32c6f9
Create Date: 2026-10-28 09:30:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c7d8e9f0a1b2'
down_revision: str | Sequence[str] | None = 'f5289d32c6f9'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('audit_log', sa.Column('customer_id', sa.String(length=64), server_default='default', nullable=False))
    op.create_index(op.f('ix_audit_log_customer_id'), 'audit_log', ['customer_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_audit_log_customer_id'), table_name='audit_log')
    op.drop_column('audit_log', 'customer_id')
