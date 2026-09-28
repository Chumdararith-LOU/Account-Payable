from dataclasses import replace
from datetime import date
from decimal import Decimal

from apmatch.schema.documents import GRNI, Invoice, LineItem, PaymentAdvice, PurchaseOrder
from apmatch.validation.arithmetic import validate_grni, validate_invoice, validate_pard, validate_po
from apmatch.validation.result import CheckCode, Severity


def _line(no, qty, price, amount):
    return LineItem(
        line_no=no,
        description=f"item {no}",
        quantity=Decimal(qty),
        unit_price=Decimal(price),
        amount=Decimal(amount),
    )


def _valid_invoice():
    lines = (_line(1, "2", "10.00", "20.00"), _line(2, "3", "5.00", "15.00"))
    return Invoice(
        invoice_number="INV-1",
        vendor_name="Vendor",
        invoice_date=date(2026, 8, 20),
        currency="USD",
        subtotal=Decimal("35.00"),
        tax_amount=Decimal("3.50"),
        total=Decimal("38.50"),
        line_items=lines,
    )


def _codes(result):
    return [f.code for f in result.checks_failed]


# --- Invoice: happy path ---------------------------------------------------


def test_invoice_happy_path():
    assert validate_invoice(_valid_invoice()).ok is True


# --- Invoice: line-level ---------------------------------------------------


def test_line_amount_mismatch():
    inv = _valid_invoice()
    bad = replace(inv.line_items[0], amount=Decimal("20.02"))  # off by $0.02
    inv = replace(inv, line_items=(bad, inv.line_items[1]))
    assert CheckCode.LINE_AMOUNT_MISMATCH in _codes(validate_invoice(inv))


def test_line_amount_within_tolerance():
    inv = _valid_invoice()
    off = replace(inv.line_items[0], amount=Decimal("20.01"))  # off by $0.01
    inv = replace(inv, line_items=(off, inv.line_items[1]))
    result = validate_invoice(inv)
    assert CheckCode.LINE_AMOUNT_MISMATCH not in _codes(result)
    assert result.ok is True


def test_no_line_items():
    inv = replace(_valid_invoice(), line_items=())
    assert CheckCode.NO_LINE_ITEMS in _codes(validate_invoice(inv))


# --- Invoice: header-level -------------------------------------------------


def test_subtotal_mismatch():
    inv = replace(_valid_invoice(), subtotal=Decimal("36.00"))
    assert CheckCode.SUBTOTAL_MISMATCH in _codes(validate_invoice(inv))


def test_total_mismatch():
    inv = replace(_valid_invoice(), total=Decimal("40.00"))
    assert CheckCode.TOTAL_MISMATCH in _codes(validate_invoice(inv))


def test_tax_mismatch():
    inv = replace(_valid_invoice(), tax_amount=Decimal("40.00"))  # tax > total
    assert CheckCode.TAX_MISMATCH in _codes(validate_invoice(inv))


def test_discount_mismatch():
    inv = replace(_valid_invoice(), discount_amount=Decimal("40.00"))  # discount > subtotal
    assert CheckCode.DISCOUNT_MISMATCH in _codes(validate_invoice(inv))


# --- Invoice: sanity -------------------------------------------------------


def test_date_in_future():
    inv = replace(_valid_invoice(), invoice_date=date(2099, 1, 1))
    result = validate_invoice(inv)
    failures = [f for f in result.checks_failed if f.code is CheckCode.DATE_IN_FUTURE]
    assert failures and failures[0].severity is Severity.WARNING


def test_missing_required_field():
    inv = replace(_valid_invoice(), invoice_number="")
    assert CheckCode.MISSING_REQUIRED_FIELD in _codes(validate_invoice(inv))


def test_negative_amount_warning():
    inv = _valid_invoice()
    neg = replace(inv.line_items[0], amount=Decimal("-20.00"))
    inv = replace(inv, line_items=(neg, inv.line_items[1]))
    result = validate_invoice(inv)
    failures = [f for f in result.checks_failed if f.code is CheckCode.NEGATIVE_AMOUNT]
    assert failures and failures[0].severity is Severity.WARNING


# --- Invoice: tax/discount rate modes --------------------------------------


def test_tax_rate_present_correct():
    inv = replace(_valid_invoice(), tax_rate=Decimal("0.10"))  # 35.00 * 0.10 == 3.50
    assert CheckCode.TAX_MISMATCH not in _codes(validate_invoice(inv))


def test_tax_rate_present_incorrect():
    inv = replace(_valid_invoice(), tax_rate=Decimal("0.10"), tax_amount=Decimal("4.00"))
    result = validate_invoice(inv)
    failures = [f for f in result.checks_failed if f.code is CheckCode.TAX_MISMATCH]
    assert failures
    assert failures[0].severity is Severity.BLOCKER
    assert failures[0].location == "header"


def test_tax_rate_absent_sanity_ok():
    inv = _valid_invoice()  # tax 3.50 < total 38.50, no tax_rate
    assert CheckCode.TAX_MISMATCH not in _codes(validate_invoice(inv))


def test_tax_rate_absent_sanity_fail():
    inv = replace(_valid_invoice(), tax_amount=Decimal("40.00"))  # tax > total
    result = validate_invoice(inv)
    failures = [f for f in result.checks_failed if f.code is CheckCode.TAX_MISMATCH]
    assert failures
    assert failures[0].severity is Severity.WARNING
    assert "sanity-only" in failures[0].location


def test_discount_rate_present_correct():
    inv = replace(
        _valid_invoice(),
        discount_amount=Decimal("3.50"),
        discount_rate=Decimal("0.10"),  # 35.00 * 0.10 == 3.50
        total=Decimal("35.00"),  # 35 - 3.50 + 3.50
    )
    result = validate_invoice(inv)
    assert CheckCode.DISCOUNT_MISMATCH not in _codes(result)
    assert result.ok is True


def test_discount_rate_present_incorrect():
    inv = replace(_valid_invoice(), discount_rate=Decimal("0.10"), discount_amount=Decimal("5.00"))
    result = validate_invoice(inv)
    failures = [f for f in result.checks_failed if f.code is CheckCode.DISCOUNT_MISMATCH]
    assert failures
    assert failures[0].severity is Severity.BLOCKER
    assert failures[0].location == "header"


def test_discount_rate_absent_sanity_fail():
    inv = replace(_valid_invoice(), discount_amount=Decimal("40.00"))  # discount > subtotal
    result = validate_invoice(inv)
    failures = [f for f in result.checks_failed if f.code is CheckCode.DISCOUNT_MISMATCH]
    assert failures
    assert failures[0].severity is Severity.WARNING
    assert "sanity-only" in failures[0].location


def test_rate_fields_default_none():
    inv = _valid_invoice()
    assert inv.tax_rate is None
    assert inv.discount_rate is None


# --- Result structure ------------------------------------------------------


def test_ok_property_true_when_no_failures():
    result = validate_invoice(_valid_invoice())
    assert result.ok is True
    assert result.checks_failed == ()


def test_has_blocker_true_when_blocker_present():
    result = validate_invoice(replace(_valid_invoice(), line_items=()))
    assert result.has_blocker is True


def test_failure_ordering():
    inv = replace(
        _valid_invoice(),
        invoice_number="",  # BLOCKER
        invoice_date=date(2099, 1, 1),  # WARNING
        tax_amount=Decimal("-1.00"),  # WARNING (negative) + arithmetic
    )
    result = validate_invoice(inv)
    ranks = {Severity.BLOCKER: 2, Severity.WARNING: 1, Severity.INFO: 0}
    keys = [(-ranks[f.severity], f.code.value, f.location) for f in result.checks_failed]
    assert keys == sorted(keys)


def test_failure_codes_are_stable():
    inv = replace(_valid_invoice(), line_items=(), invoice_number="")
    result = validate_invoice(inv)
    assert result.checks_failed
    for f in result.checks_failed:
        assert isinstance(f.code, CheckCode)
        assert f.code.name in CheckCode.__members__


# --- None-handling: missing fields emit MISSING_REQUIRED_FIELD, never crash ---


def _missing_fields(result):
    return [f for f in result.checks_failed if f.code is CheckCode.MISSING_REQUIRED_FIELD]


def test_invoice_tax_amount_none_emits_missing_not_crash():
    inv = replace(_valid_invoice(), tax_amount=None)
    result = validate_invoice(inv)  # must not raise
    assert result.has_blocker is True
    assert any(f.actual == "tax_amount" for f in _missing_fields(result))


def test_invoice_subtotal_none_emits_missing_not_crash():
    inv = replace(_valid_invoice(), subtotal=None)
    result = validate_invoice(inv)
    assert result.has_blocker is True
    assert any(f.actual == "subtotal" for f in _missing_fields(result))


def test_invoice_total_none_emits_missing_not_crash():
    inv = replace(_valid_invoice(), total=None)
    result = validate_invoice(inv)
    assert result.has_blocker is True
    assert any(f.actual == "total" for f in _missing_fields(result))


def test_invoice_line_amount_none_emits_missing_not_crash():
    base = _valid_invoice()
    bad = replace(base.line_items[0], amount=None)
    inv = replace(base, line_items=(bad, base.line_items[1]))
    result = validate_invoice(inv)
    assert result.has_blocker is True
    assert any(f.location == "line 1" and f.actual == "amount" for f in _missing_fields(result))


def test_invoice_line_unit_price_none_emits_missing_not_crash():
    base = _valid_invoice()
    bad = replace(base.line_items[0], unit_price=None)
    inv = replace(base, line_items=(bad, base.line_items[1]))
    result = validate_invoice(inv)
    assert result.has_blocker is True
    assert any(f.location == "line 1" and f.actual == "unit_price" for f in _missing_fields(result))


def test_invoice_multiple_missing_fields():
    inv = replace(_valid_invoice(), subtotal=None, tax_amount=None)
    missing = _missing_fields(validate_invoice(inv))
    assert len(missing) == 2
    assert {f.actual for f in missing} == {"subtotal", "tax_amount"}


def test_invoice_missing_field_does_not_emit_arithmetic_failure():
    inv = replace(_valid_invoice(), tax_amount=None)
    codes = [f.code for f in validate_invoice(inv).checks_failed]
    assert CheckCode.TAX_MISMATCH not in codes
    assert CheckCode.TOTAL_MISMATCH not in codes


def test_invoice_empty_string_currency_emits_missing():
    inv = replace(_valid_invoice(), currency="")
    result = validate_invoice(inv)
    assert result.has_blocker is True
    assert any(f.actual == "currency" for f in _missing_fields(result))


def test_po_none_fields_emit_missing_not_crash():
    po = PurchaseOrder(
        po_number="PO-1",
        vendor_name="Vendor",
        po_date=date(2026, 8, 15),
        total=None,
        line_items=(LineItem(line_no=1, description="X", quantity=Decimal("1"), unit_price=Decimal("10.00")),),
    )
    result = validate_po(po)
    assert result.has_blocker is True
    assert any(f.actual == "total" for f in _missing_fields(result))


def test_grni_none_qty_emits_missing_not_crash():
    g = GRNI(
        grn_number="GRN-1",
        vendor_name="Vendor",
        grni_date=date(2026, 8, 19),
        line_items=(LineItem(line_no=1, description="X", quantity=None),),
    )
    result = validate_grni(g)
    assert result.has_blocker is True
    assert any(f.location == "line 1" and f.actual == "quantity" for f in _missing_fields(result))


def test_pard_none_amount_emits_missing_not_crash():
    p = PaymentAdvice(
        pard_number="PARD-1",
        invoice_number="INV-1",
        amount=None,
        payment_date=date(2026, 8, 25),
    )
    result = validate_pard(p)
    assert result.has_blocker is True
    assert any(f.actual == "amount" for f in _missing_fields(result))


def test_missing_required_field_sorts_before_arithmetic():
    inv = replace(_valid_invoice(), subtotal=Decimal("36.00"), tax_amount=None)
    result = validate_invoice(inv)
    codes = [f.code for f in result.checks_failed]
    assert CheckCode.MISSING_REQUIRED_FIELD in codes
    assert CheckCode.SUBTOTAL_MISMATCH in codes
    assert codes.index(CheckCode.MISSING_REQUIRED_FIELD) < codes.index(CheckCode.SUBTOTAL_MISMATCH)
