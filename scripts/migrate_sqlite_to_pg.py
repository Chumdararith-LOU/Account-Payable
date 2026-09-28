"""DEV-ONLY one-shot migration: legacy SQLite (ap_automation.db) -> Postgres.

This is fixture-data migration for demos and integration smoke tests. It is
NOT a production upgrade path. Production schema changes go through Alembic.

- Reads from ap_automation.db (SQLite, opened read-only).
- Writes via apmatch.store.repositories (P1-10b).
- Float -> Decimal conversion uses ``Decimal(str(value))`` — the ONLY place in
  the codebase where this pattern is expected. It preserves the source float's
  decimal representation so 1100.0 does not become 1099.9999999998.
- Idempotent: running twice produces the same result (repositories UPSERT).

Legacy -> P1-06 adaptations (the legacy schema is a subset of the dataclass):
- INVOICE_HEADER has no ``currency`` column: currency defaults to "USD".
- PARD.INV_ID in the legacy DB is a data-entry error (it equals PARD_ID); when
  it does not match any invoice and exactly one invoice exists, the PARD is
  remapped to that invoice so the FK holds.
- Line ``line_no`` is taken from the legacy AUTOINCREMENT id (unique per doc).

Derivation policy
-----------------
The legacy schema stores only the inputs of the money calculation (quantity,
unit_price) and a header total that is frequently unset. The P1-06 schema
requires the outputs explicitly (line.amount, header.subtotal, header.total).
The migrator therefore:

- PRESERVES any explicit source value that is non-zero.
- DERIVES from source when the target field has no source column or the source
  value is zero and lines exist:
    * line.amount      = quantity * unit_price
    * header.subtotal  = sum(line.amount)
    * header.total     = subtotal + tax - discount

This is not "fixing" the data; it is translating implied semantics into
explicit ones. It is documented here because it is the only place in the
codebase where source data is augmented during migration. Quantization reuses
``MONEY_QUANTUM`` / ``ROUND_HALF_UP`` from the dataclass layer (no second
rounding constant).
"""

from __future__ import annotations

import os
import sqlite3
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from apmatch.schema.documents import (  # noqa: E402
    GRNI,
    Invoice,
    LineItem,
    MONEY_QUANTUM,
    PaymentAdvice,
    PurchaseOrder,
    ROUND_HALF_UP,
)
from apmatch.store.repositories import (
    GRNIRepository,
    InvoiceRepository,
    PaymentAdviceRepository,
    PurchaseOrderRepository,
)

DEFAULT_DB = REPO_ROOT / "ap_automation.db"
DEFAULT_URL = "postgresql+psycopg://apmatch:apmatch_dev_only@localhost:5433/apmatch"

SUMMARY_KEYS = (
    "invoice_headers",
    "invoice_lines",
    "po_headers",
    "po_lines",
    "grni_headers",
    "grni_lines",
    "pard",
)


def _dec(value) -> Decimal | None:
    """Return None if value is None, else ``Decimal(str(value))``.

    ``Decimal(str(value))`` is the ONLY place in the codebase where this
    pattern is expected: it preserves the source float's decimal
    representation (e.g. 1100.0 stays 1100.0, not 1099.9999999998).
    """
    if value is None:
        return None
    return Decimal(str(value))


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%d-%b-%Y").date()


def _derive_line_amount(qty, price, legacy_amount) -> Decimal | None:
    """line.amount: preserve a non-zero source value, else derive qty * price.

    Reuses the dataclass layer's ``MONEY_QUANTUM`` / ``ROUND_HALF_UP``.
    """
    if legacy_amount is not None and legacy_amount != 0:
        return Decimal(str(legacy_amount))
    if qty is None or price is None:
        return None
    return (qty * price).quantize(MONEY_QUANTUM, ROUND_HALF_UP)


def _load_sqlite(db_path: Path) -> dict[str, list[dict]]:
    """Read every user table into a dict keyed by table name (stdlib sqlite3).

    Opens the DB read-only (``mode=ro``) so the legacy file is never modified.
    """
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        tables = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        ]
        return {t: [dict(r) for r in conn.execute(f"SELECT * FROM {t}")] for t in tables}
    finally:
        conn.close()


def _sqlite_to_invoice(row: dict, line_rows: list[dict]) -> Invoice:
    total = _dec(row["Total"])
    tax = _dec(row["Tax"])
    lines = tuple(
        LineItem(
            line_no=r["INV_LINE_ID"],
            description=r["Item"],
            quantity=_dec(r["Qty"]),
            unit_price=_dec(r["Price"]),
            # legacy INVOICE_LINE has no Amount column -> derive qty * price
            amount=_derive_line_amount(_dec(r["Qty"]), _dec(r["Price"]), None),
            unit_of_measure=None,
        )
        for r in line_rows
    )
    if total is None or total == 0:
        # Derive: subtotal = sum(line.amount); total = subtotal + tax (no discount column).
        subtotal = sum((li.amount for li in lines if li.amount is not None), Decimal("0"))
        total = (subtotal + (tax or Decimal("0"))).quantize(MONEY_QUANTUM, ROUND_HALF_UP)
    else:
        subtotal = (total - (tax or Decimal("0"))).quantize(MONEY_QUANTUM, ROUND_HALF_UP)
    return Invoice(
        invoice_number=row["INV_ID"],
        vendor_name=row["Vendor"],
        invoice_date=_parse_date(row["Date"]),
        currency="USD",  # legacy INVOICE_HEADER has no currency column
        subtotal=subtotal,
        tax_amount=tax if tax is not None else Decimal("0"),
        total=total,
        line_items=lines,
    )


def _sqlite_to_po(row: dict, line_rows: list[dict]) -> PurchaseOrder:
    total = _dec(row["Total"])
    lines = tuple(
        LineItem(
            line_no=r["PO_LINE_ID"],
            description=r["Item"],
            quantity=_dec(r["Qty"]),
            unit_price=_dec(r["Price"]),
            # legacy PO_LINE has no Amount column -> derive qty * price
            amount=_derive_line_amount(_dec(r["Qty"]), _dec(r["Price"]), None),
            unit_of_measure=None,
        )
        for r in line_rows
    )
    if total is None or total == 0:
        # Derive: total = sum(line.amount).
        total = sum((li.amount for li in lines if li.amount is not None), Decimal("0")).quantize(
            MONEY_QUANTUM, ROUND_HALF_UP
        )
    return PurchaseOrder(
        po_number=row["PO_ID"],
        vendor_name=row["Vendor"],
        po_date=_parse_date(row["Date"]),
        total=total,
        line_items=lines,
        currency="USD",  # legacy PO_HEADER has no currency column
    )


def _sqlite_to_grni(row: dict, line_rows: list[dict]) -> GRNI:
    lines = tuple(
        LineItem(
            line_no=r["GRNI_LINE_ID"],
            description=r["Item"],
            quantity=_dec(r["Qty"]),
            unit_price=None,  # GRNI lines carry quantity only
            amount=None,
            unit_of_measure=None,
        )
        for r in line_rows
    )
    return GRNI(
        grn_number=row["GRNI_ID"],
        vendor_name=row["Vendor"],
        grni_date=_parse_date(row["Date"]),
        line_items=lines,
    )


def _sqlite_to_pard(
    row: dict, invoice_numbers: set[str], invoice_totals: dict[str, Decimal]
) -> PaymentAdvice:
    inv_id = row["INV_ID"]
    if inv_id not in invoice_numbers:
        if len(invoice_numbers) == 1:
            inv_id = next(iter(invoice_numbers))
        else:
            raise ValueError(
                f"PARD {row['PARD_ID']!r} references unknown invoice {inv_id!r}; "
                f"cannot remap (invoices present: {sorted(invoice_numbers)})"
            )
    amount = _dec(row["Amount"])
    if amount is None or amount == 0:
        # Derive from the referenced invoice's total when the PARD amount is unset.
        amount = invoice_totals.get(inv_id, Decimal("0"))
    return PaymentAdvice(
        pard_number=row["PARD_ID"],
        invoice_number=inv_id,
        amount=amount,
        payment_date=_parse_date(row["Date"]),
        reference=row["Ref"],
        currency=None,  # legacy PARD has no currency column
    )


def migrate(db_path: Path, session: Session) -> dict[str, int]:
    """Migrate every document kind from SQLite into Postgres via repositories.

    Returns a per-document-kind count of rows written. The caller commits.
    """
    data = _load_sqlite(db_path)
    counts: dict[str, int] = {}

    # Delete existing PARDs first: they reference invoices, and the invoice
    # upsert (delete-then-insert) cannot delete a header a PARD still
    # references. Clearing the PARDs first releases the FK so the invoice
    # upsert succeeds; the PARDs are re-inserted after the invoices below.
    pard_rows = data.get("PARD", [])
    for row in pard_rows:
        PaymentAdviceRepository.delete(session, row["PARD_ID"])

    invoice_rows = data.get("INVOICE_HEADER", [])
    invoice_lines = data.get("INVOICE_LINE", [])
    invoice_numbers: set[str] = set()
    invoice_totals: dict[str, Decimal] = {}
    for row in invoice_rows:
        lines = [l for l in invoice_lines if l["INV_ID"] == row["INV_ID"]]
        inv = _sqlite_to_invoice(row, lines)
        InvoiceRepository.save(session, inv)
        invoice_numbers.add(inv.invoice_number)
        invoice_totals[inv.invoice_number] = inv.total
    counts["invoice_headers"] = len(invoice_rows)
    counts["invoice_lines"] = len(invoice_lines)

    po_rows = data.get("PO_HEADER", [])
    po_lines = data.get("PO_LINE", [])
    for row in po_rows:
        lines = [l for l in po_lines if l["PO_ID"] == row["PO_ID"]]
        PurchaseOrderRepository.save(session, _sqlite_to_po(row, lines))
    counts["po_headers"] = len(po_rows)
    counts["po_lines"] = len(po_lines)

    grni_rows = data.get("GRNI_HEADER", [])
    grni_lines = data.get("GRNI_LINE", [])
    for row in grni_rows:
        lines = [l for l in grni_lines if l["GRNI_ID"] == row["GRNI_ID"]]
        GRNIRepository.save(session, _sqlite_to_grni(row, lines))
    counts["grni_headers"] = len(grni_rows)
    counts["grni_lines"] = len(grni_lines)

    for row in pard_rows:
        PaymentAdviceRepository.save(session, _sqlite_to_pard(row, invoice_numbers, invoice_totals))
    counts["pard"] = len(pard_rows)

    return counts


def main() -> int:
    load_dotenv()
    url = os.environ.get("DATABASE_URL", DEFAULT_URL)
    db_path = Path(os.environ.get("SQLITE_DB", str(DEFAULT_DB)))
    engine = create_engine(url)
    try:
        with Session(engine) as session:
            counts = migrate(db_path, session)
            session.commit()
    except Exception as exc:  # noqa: BLE001 - report any per-document failure
        print(f"migration failed: {exc}", file=sys.stderr)
        return 1
    for key in SUMMARY_KEYS:
        print(f"{key}: {counts.get(key, 0)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
