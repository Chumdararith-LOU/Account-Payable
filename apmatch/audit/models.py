"""SQLAlchemy 2.x ORM model for the append-only audit log.

Extends the existing ``Base`` from ``apmatch.store.models`` so the audit_log
table lives in the same metadata (Alembic autogenerates against it).

Deliberately NO foreign keys. The audit log is an independent record; if a
document is later deleted, the audit row must survive. This is the single most
important design decision in this table.

No UPDATE or DELETE is possible at the code layer (the repository provides
neither). Postgres-level permission enforcement is a P1-12 concern (production
DBA).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Numeric, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from apmatch.store.models import Base


class AuditLog(Base):
    __tablename__ = "audit_log"

    run_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    run_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    invoice_number: Mapped[str] = mapped_column(String(64), nullable=False)
    po_number: Mapped[str | None] = mapped_column(String(64))
    grn_number: Mapped[str | None] = mapped_column(String(64))
    pard_ref: Mapped[str | None] = mapped_column(String(64))
    route: Mapped[str] = mapped_column(String(16), nullable=False)
    route_reason: Mapped[str] = mapped_column(String(32), nullable=False)
    score_value: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    remark: Mapped[str] = mapped_column(String(1024), nullable=False)
    validation_failures: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    match_failures: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    # JSONB array. Each element is a dict with:
    #   location, invoice_text, counterpart_text,
    #   score, threshold_review, threshold_accept,
    #   band, model_version
    # Mirrors the SimilarityMatch dataclass in
    # apmatch/matching/result.py.
    similarity_matches: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
