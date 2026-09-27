import apmatch.remarks.matching as m
import pytest
from apmatch.matching.result import MatchCode, MatchFailure, MatchResult, Outcome
from apmatch.remarks.matching import MATCH_TEMPLATES, remark_for_match, summarize_match
from apmatch.validation.result import Severity


# --- Coverage --------------------------------------------------------------


def test_all_matchcodes_have_template():
    for code in MatchCode:
        assert code in MATCH_TEMPLATES, f"{code.value} has no template"


def test_no_orphan_match_templates():
    valid = set(MatchCode)
    for key in MATCH_TEMPLATES:
        assert key in valid, f"orphan template key {key!r}"


def test_match_templates_end_with_period():
    for code, tpl in MATCH_TEMPLATES.items():
        assert tpl.endswith("."), f"{code.value} template does not end with a period"


def test_match_templates_are_single_line():
    for code, tpl in MATCH_TEMPLATES.items():
        assert "\n" not in tpl, f"{code.value} template is not single-line"


# --- remark_for_match ------------------------------------------------------


def test_remark_for_match_qty_mismatch():
    f = MatchFailure(MatchCode.QTY_MISMATCH, Severity.WARNING, "line 2 (INV) -> line 2 (PO)", "15", "20", "5")
    assert remark_for_match(f) == "Quantity mismatch at line 2 (INV) -> line 2 (PO): expected 15, actual 20."


def test_remark_for_match_no_matching_po_line():
    f = MatchFailure(MatchCode.NO_MATCHING_PO_LINE, Severity.WARNING, "line 4 (INV)", "a PO line", "none", "")
    assert remark_for_match(f) == "No matching PO line for line 4 (INV)."


def test_remark_for_match_vendor_mismatch():
    f = MatchFailure(MatchCode.VENDOR_MISMATCH, Severity.WARNING, "header", "mekong supplies co., ltd", "other vendor co", "")
    assert remark_for_match(f) == "Vendor mismatch: mekong supplies co., ltd vs other vendor co."


def test_remark_unknown_match_code_raises():
    saved = m.MATCH_TEMPLATES[MatchCode.PO_MISSING]
    del m.MATCH_TEMPLATES[MatchCode.PO_MISSING]
    try:
        f = MatchFailure(MatchCode.PO_MISSING, Severity.BLOCKER, "header", "present", "missing", "")
        with pytest.raises(KeyError):
            remark_for_match(f)
    finally:
        m.MATCH_TEMPLATES[MatchCode.PO_MISSING] = saved


# --- summarize_match -------------------------------------------------------


def test_summarize_match_outcome_match_is_positive():
    r = MatchResult(Outcome.MATCH, 1.0, (), "INV-1")
    assert summarize_match(r) == "All documents match."


def test_summarize_match_pending_info_prefix():
    f = MatchFailure(MatchCode.PO_MISSING, Severity.BLOCKER, "header", "present", "missing", "")
    r = MatchResult(Outcome.PENDING_INFO, 0.0, (f,), "INV-1")
    assert summarize_match(r) == "Awaiting information: Purchase order not found."


def test_summarize_match_single_failure():
    f = MatchFailure(MatchCode.VENDOR_MISMATCH, Severity.WARNING, "header", "a", "b", "")
    r = MatchResult(Outcome.DISCREPANCY, 0.7, (f,), "INV-1")
    assert summarize_match(r) == "Vendor mismatch: a vs b."


def test_summarize_match_multiple_failures_uses_first():
    blocker = MatchFailure(MatchCode.PARD_AMOUNT_MISMATCH, Severity.BLOCKER, "header", "1100.00", "999.50", "100.50")
    warning = MatchFailure(MatchCode.VENDOR_MISMATCH, Severity.WARNING, "header", "a", "b", "")
    r = MatchResult(Outcome.DISCREPANCY, 0.4, (blocker, warning), "INV-1")
    assert summarize_match(r) == (
        "2 issue(s). Most severe: Payment advice amount mismatch: expected 1100.00, actual 999.50 (off by 100.50)."
    )


def test_summarize_match_deterministic():
    f = MatchFailure(MatchCode.QTY_MISMATCH, Severity.WARNING, "line 1 (INV) -> line 1 (PO)", "10", "9", "1")
    r = MatchResult(Outcome.DISCREPANCY, 0.7, (f,), "INV-1")
    assert summarize_match(r) == summarize_match(r)
