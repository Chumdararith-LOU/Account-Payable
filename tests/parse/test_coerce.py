"""Field coercion: parse_money, parse_qty, parse_date, parse_document_number."""

from datetime import date
from decimal import Decimal

from apmatch.parse.coerce import (
    parse_date,
    parse_document_number,
    parse_money,
    parse_qty,
)


def test_parse_money_happy():
    assert parse_money("1,000.00") == Decimal("1000.00")
    assert parse_money("1000") == Decimal("1000")
    assert parse_money("$1,000.00") == Decimal("1000.00")
    assert parse_money("USD 1,000.00") == Decimal("1000.00")


def test_parse_money_noise():
    assert parse_money("  $ 1,100.00 ") == Decimal("1100.00")


def test_parse_money_failure():
    assert parse_money("") is None
    assert parse_money(None) is None
    assert parse_money("n/a") is None


def test_parse_money_rejects_european_format():
    # "1.000,00" is ambiguous (dot as thousands separator); reject rather
    # than silently mis-parse (D-043 discipline: never guess).
    assert parse_money("1.000,00") is None


def test_parse_qty_happy():
    assert parse_qty("10") == Decimal("10")
    assert parse_qty("10.0") == Decimal("10.0")
    assert parse_qty("1,000") == Decimal("1000")


def test_parse_qty_noise():
    assert parse_qty("10 pcs") == Decimal("10")


def test_parse_qty_failure():
    assert parse_qty("") is None
    assert parse_qty(None) is None
    assert parse_qty("n/a") is None


def test_parse_date_happy():
    assert parse_date("15-Aug-2026") == date(2026, 8, 15)
    assert parse_date("2026-08-15") == date(2026, 8, 15)
    assert parse_date("15/08/2026") == date(2026, 8, 15)


def test_parse_date_failure():
    assert parse_date("") is None
    assert parse_date(None) is None
    assert parse_date("n/a") is None


def test_parse_date_ambiguous_mm_dd_vs_dd_mm():
    # DD/MM is tried before MM/DD (D-043): the AP corpus in Cambodia and the
    # region is DD/MM. So 03/04/2026 is 3 April 2026, not 4 March.
    assert parse_date("03/04/2026") == date(2026, 4, 3)
    # A date that can only be MM/DD (day > 12) still parses via the fallback.
    assert parse_date("08/15/2026") == date(2026, 8, 15)


def test_parse_document_number_happy():
    assert parse_document_number("INV-2026-1123") == "INV-2026-1123"
    assert parse_document_number("PO- 2026-0451") == "PO-2026-0451"
    assert parse_document_number("GRN-2026-0322.") == "GRN-2026-0322"


def test_parse_document_number_failure():
    assert parse_document_number("") is None
    assert parse_document_number(None) is None
