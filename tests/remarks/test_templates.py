import pytest

from apmatch.remarks.templates import TEMPLATES, remark_for, summarize
from apmatch.validation.result import CheckCode, CheckFailure, Severity, ValidationResult


def _failure(code, location="header", expected="", actual="", delta=""):
    return CheckFailure(code=code, severity=Severity.BLOCKER, location=location, expected=expected, actual=actual, delta=delta)


# --- Coverage & registry ---------------------------------------------------


def test_all_checkcodes_have_template():
    for c in CheckCode:
        assert c in TEMPLATES


def test_no_orphan_templates():
    valid = set(CheckCode)
    for key in TEMPLATES:
        assert key in valid


def test_templates_end_with_period():
    for t in TEMPLATES.values():
        assert t.endswith(".")


def test_templates_are_single_line():
    for t in TEMPLATES.values():
        assert "\n" not in t


# --- remark_for ------------------------------------------------------------


def test_remark_for_subtotal_mismatch():
    f = _failure(CheckCode.SUBTOTAL_MISMATCH, expected="1000.00", actual="450.00", delta="550.00")
    assert remark_for(f) == "Subtotal mismatch: expected 1000.00, actual 450.00 (off by 550.00)."


def test_remark_for_missing_required_field():
    f = _failure(CheckCode.MISSING_REQUIRED_FIELD, actual="invoice_number")
    assert remark_for(f) == "Missing required field at header: invoice_number."


def test_remark_for_negative_amount():
    f = _failure(CheckCode.NEGATIVE_AMOUNT, actual="subtotal")
    assert remark_for(f) == "Negative amount at header: subtotal."


def test_remark_unknown_code_raises():
    saved = TEMPLATES.pop(CheckCode.SUBTOTAL_MISMATCH)
    try:
        f = _failure(CheckCode.SUBTOTAL_MISMATCH)
        with pytest.raises(KeyError):
            remark_for(f)
    finally:
        TEMPLATES[CheckCode.SUBTOTAL_MISMATCH] = saved


# --- summarize -------------------------------------------------------------


def test_summarize_empty_result_is_ok():
    r = ValidationResult(document_kind="invoice", checks_passed=(), checks_failed=())
    assert summarize(r) == "Validated OK."


def test_summarize_single_failure_is_that_remark():
    f = _failure(CheckCode.NO_LINE_ITEMS, actual="0 lines")
    r = ValidationResult(document_kind="invoice", checks_passed=(), checks_failed=(f,))
    assert summarize(r) == remark_for(f)
    assert summarize(r) == "No line items present."


def test_summarize_multiple_failures_prefixed_with_count():
    f1 = _failure(CheckCode.SUBTOTAL_MISMATCH, expected="1000.00", actual="450.00", delta="550.00")
    f2 = _failure(CheckCode.DATE_IN_FUTURE, actual="2099-01-01")
    r = ValidationResult(document_kind="invoice", checks_passed=(), checks_failed=(f1, f2))
    assert summarize(r).startswith("2 issue(s). Most severe: ")


def test_summarize_uses_first_failure_as_most_severe():
    f1 = _failure(CheckCode.SUBTOTAL_MISMATCH, expected="1000.00", actual="450.00", delta="550.00")
    f2 = _failure(CheckCode.DATE_IN_FUTURE, actual="2099-01-01")
    r = ValidationResult(document_kind="invoice", checks_passed=(), checks_failed=(f1, f2))
    assert summarize(r) == f"2 issue(s). Most severe: {remark_for(f1)}"


# --- Determinism -----------------------------------------------------------


def test_summarize_deterministic():
    f = _failure(CheckCode.TOTAL_MISMATCH, expected="1100.00", actual="999.00", delta="101.00")
    r = ValidationResult(document_kind="invoice", checks_passed=(), checks_failed=(f,))
    assert summarize(r) == summarize(r)


def test_remark_for_deterministic():
    f = _failure(CheckCode.TAX_MISMATCH, expected="100.00", actual="100.02", delta="0.02")
    assert remark_for(f) == remark_for(f)


# --- i18n hook -------------------------------------------------------------


def test_summarize_accepts_lang_but_currently_ignores_it():
    f = _failure(CheckCode.NO_LINE_ITEMS, actual="0 lines")
    r = ValidationResult(document_kind="invoice", checks_passed=(), checks_failed=(f,))
    assert summarize(r, lang="km") == summarize(r, lang="en")
