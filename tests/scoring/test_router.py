from apmatch.matching.result import MatchCode, MatchFailure, MatchResult, Outcome
from apmatch.scoring.result import Route, RouteReason
from apmatch.scoring.router import decide
from apmatch.validation.result import CheckCode, CheckFailure, Severity, ValidationResult


def _failure(code: CheckCode, severity: Severity) -> CheckFailure:
    return CheckFailure(code, severity, "header", "e", "a", "")


def _validation(*failures: CheckFailure) -> ValidationResult:
    return ValidationResult("invoice", (), tuple(failures))


def _match(score: float, outcome: Outcome, *failures: MatchFailure) -> MatchResult:
    return MatchResult(outcome, score, tuple(failures), "INV-1")


def _ok_validation() -> ValidationResult:
    return _validation()


def _blocker_validation() -> ValidationResult:
    return _validation(_failure(CheckCode.TOTAL_MISMATCH, Severity.BLOCKER))


def _warning_validation(n: int = 1) -> ValidationResult:
    return _validation(*[_failure(CheckCode.NEGATIVE_AMOUNT, Severity.WARNING) for _ in range(n)])


def _match_ok() -> MatchResult:
    return _match(1.0, Outcome.MATCH)


def _pending_match() -> MatchResult:
    return _match(0.0, Outcome.PENDING_INFO, MatchFailure(MatchCode.PO_MISSING, Severity.BLOCKER, "header", "present", "missing", ""))


def _discrepancy_match() -> MatchResult:
    return _match(0.7, Outcome.DISCREPANCY, MatchFailure(MatchCode.VENDOR_MISMATCH, Severity.WARNING, "header", "a", "b", ""))


def test_reject_when_validation_has_blocker():
    d = decide(_blocker_validation(), _match_ok(), None)
    assert d.route is Route.REJECT
    assert d.reason is RouteReason.VALIDATION_BLOCKER


def test_pending_info_routes_to_human():
    d = decide(_ok_validation(), _pending_match(), None)
    assert d.route is Route.HUMAN_REVIEW
    assert d.reason is RouteReason.MATCH_PENDING_INFO


def test_discrepancy_routes_to_human():
    d = decide(_ok_validation(), _discrepancy_match(), None)
    assert d.route is Route.HUMAN_REVIEW
    assert d.reason is RouteReason.MATCH_DISCREPANCY


def test_low_ocr_confidence_routes_to_human():
    d = decide(_ok_validation(), _match_ok(), 0.5)
    assert d.route is Route.HUMAN_REVIEW
    assert d.reason is RouteReason.LOW_OCR_CONFIDENCE


def test_low_score_routes_to_human():
    # No blocker + MATCH, but two warnings drag the combined score below
    # AUTO_APPROVE_SCORE_MIN (0.375*0.6 + 0.625*1.0 = 0.85 < 0.90).
    d = decide(_warning_validation(2), _match_ok(), None)
    assert d.route is Route.HUMAN_REVIEW
    assert d.reason is RouteReason.LOW_OVERALL_SCORE


def test_auto_approve_when_all_good():
    d = decide(_ok_validation(), _match_ok(), 0.95)
    assert d.route is Route.AUTO_APPROVE
    assert d.reason is RouteReason.ALL_CHECKS_PASSED


def test_reject_precedes_all_other_checks():
    d = decide(_blocker_validation(), _discrepancy_match(), 0.5)
    assert d.route is Route.REJECT
    assert d.reason is RouteReason.VALIDATION_BLOCKER


def test_decision_deterministic():
    a = decide(_ok_validation(), _match_ok(), 0.95)
    b = decide(_ok_validation(), _match_ok(), 0.95)
    assert a == b


def test_route_reason_pair_is_valid():
    valid_pairs = {
        (Route.AUTO_APPROVE, RouteReason.ALL_CHECKS_PASSED),
        (Route.REJECT, RouteReason.VALIDATION_BLOCKER),
        (Route.HUMAN_REVIEW, RouteReason.MATCH_PENDING_INFO),
        (Route.HUMAN_REVIEW, RouteReason.MATCH_DISCREPANCY),
        (Route.HUMAN_REVIEW, RouteReason.LOW_OCR_CONFIDENCE),
        (Route.HUMAN_REVIEW, RouteReason.LOW_OVERALL_SCORE),
    }
    cases = [
        (_ok_validation(), _match_ok(), 0.95),
        (_ok_validation(), _match_ok(), None),
        (_blocker_validation(), _match_ok(), None),
        (_ok_validation(), _pending_match(), None),
        (_ok_validation(), _discrepancy_match(), None),
        (_ok_validation(), _match_ok(), 0.5),
        (_warning_validation(2), _match_ok(), None),
    ]
    for validation, match, ocr in cases:
        d = decide(validation, match, ocr)
        assert (d.route, d.reason) in valid_pairs
