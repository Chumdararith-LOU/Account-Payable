"""extraction_source column

Revision ID: d4e5f6a7b8c9
Revises: c7d8e9f0a1b2
Create Date: 2026-11-01 22:30:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: str | Sequence[str] | None = 'c7d8e9f0a1b2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('audit_log', sa.Column('extraction_source', sa.String(length=16), server_default='vlm', nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('audit_log', 'extraction_source')
