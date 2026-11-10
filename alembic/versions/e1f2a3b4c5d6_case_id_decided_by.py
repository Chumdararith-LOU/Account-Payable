"""case_id and decided_by on audit_log (review workflow)

Revision ID: e1f2a3b4c5d6
Revises: d4e5f6a7b8c9
Create Date: 2026-11-10 23:40:00.000000

A case is one submission (invoice + PO + GRN + payment advice). Its first run
has case_id == run_id; every reviewer correction or decision is a NEW audit row
with the same case_id (the log stays append-only). decided_by says who made the
route decision: "system" or "reviewer". A NULL case_id means the run is its
own case; queries use COALESCE(case_id, run_id).
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e1f2a3b4c5d6"
down_revision: str | Sequence[str] | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("audit_log", sa.Column("case_id", sa.String(length=32), nullable=True))
    op.add_column(
        "audit_log",
        sa.Column("decided_by", sa.String(length=16), server_default="system", nullable=False),
    )
    op.create_index("ix_audit_log_case_id", "audit_log", ["case_id"])


def downgrade() -> None:
    op.drop_index("ix_audit_log_case_id", table_name="audit_log")
    op.drop_column("audit_log", "decided_by")
    op.drop_column("audit_log", "case_id")
