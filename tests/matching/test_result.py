from apmatch.matching.result import MatchCode, MatchFailure, MatchResult, Outcome
from apmatch.validation.result import Severity


def test_ok_true_when_no_failures():
    r = MatchResult(Outcome.MATCH, 1.0, (), "INV-1")
    assert r.ok is True
    assert r.has_blocker is False
    assert r.is_pending is False


def test_has_blocker_true_when_any_blocker():
    r = MatchResult(
        Outcome.DISCREPANCY,
        0.5,
        (MatchFailure(MatchCode.PARD_AMOUNT_MISMATCH, Severity.BLOCKER, "header", "1100.00", "999.50", "100.50"),),
        "INV-1",
    )
    assert r.has_blocker is True
    assert r.ok is False


def test_is_pending_true_when_pending_info():
    r = MatchResult(Outcome.PENDING_INFO, 0.0, (), "INV-1")
    assert r.is_pending is True
    assert r.ok is False
