import pytest

from apmatch.matching.result import MatchResult, Outcome
from apmatch.scoring.confidence import combined_score, match_component, validation_component
from apmatch.validation.result import CheckCode, CheckFailure, Severity, ValidationResult


def _failure(code: CheckCode, severity: Severity) -> CheckFailure:
    return CheckFailure(code, severity, "header", "e", "a", "")


def _validation(*failures: CheckFailure) -> ValidationResult:
    return ValidationResult("invoice", (), tuple(failures))


def _match(score: float, outcome: Outcome = Outcome.MATCH) -> MatchResult:
    return MatchResult(outcome, score, (), "INV-1")


# --- validation_component --------------------------------------------------


def test_validation_component_zero_failures():
    assert validation_component(_validation()) == 1.0


def test_validation_component_one_blocker():
    assert validation_component(_validation(_failure(CheckCode.TOTAL_MISMATCH, Severity.BLOCKER))) == 0.5


def test_validation_component_two_blockers():
    v = _validation(
        _failure(CheckCode.TOTAL_MISMATCH, Severity.BLOCKER),
        _failure(CheckCode.SUBTOTAL_MISMATCH, Severity.BLOCKER),
    )
    assert validation_component(v) == 0.0


def test_validation_component_warning_only():
    assert validation_component(_validation(_failure(CheckCode.NEGATIVE_AMOUNT, Severity.WARNING))) == 0.8


def test_validation_component_mixed():
    v = _validation(
        _failure(CheckCode.TOTAL_MISMATCH, Severity.BLOCKER),
        _failure(CheckCode.NEGATIVE_AMOUNT, Severity.WARNING),
        _failure(CheckCode.DATE_IN_FUTURE, Severity.INFO),
    )
    assert validation_component(v) == pytest.approx(0.25)  # 1.0 - 0.5 - 0.2 - 0.05


def test_validation_component_clamped_below_zero():
    v = _validation(
        _failure(CheckCode.TOTAL_MISMATCH, Severity.BLOCKER),
        _failure(CheckCode.SUBTOTAL_MISMATCH, Severity.BLOCKER),
        _failure(CheckCode.TAX_MISMATCH, Severity.BLOCKER),
    )
    assert validation_component(v) == 0.0  # 1.0 - 1.5 clamped to 0.0


# --- match_component -------------------------------------------------------


def test_match_component_passes_through():
    assert match_component(_match(0.7)) == 0.7


# --- combined_score --------------------------------------------------------


def test_combined_score_no_ocr_renormalizes():
    # v=1.0, m=0.0 -> 0.375*1.0 + 0.625*0.0 = 0.375 (renormalized), not 0.3.
    s = combined_score(_validation(), _match(0.0), None)
    assert s.value == pytest.approx(0.375)
    assert s.ocr_component is None


def test_combined_score_with_ocr():
    s = combined_score(_validation(), _match(1.0), 0.5)
    assert s.value == pytest.approx(0.3 * 1.0 + 0.5 * 1.0 + 0.2 * 0.5)  # 0.9
    assert s.ocr_component == 0.5


def test_combined_score_rejects_out_of_range_ocr():
    with pytest.raises(ValueError):
        combined_score(_validation(), _match(1.0), 1.5)


def test_combined_score_deterministic():
    a = combined_score(_validation(_failure(CheckCode.NEGATIVE_AMOUNT, Severity.WARNING)), _match(0.6), 0.9)
    b = combined_score(_validation(_failure(CheckCode.NEGATIVE_AMOUNT, Severity.WARNING)), _match(0.6), 0.9)
    assert a == b


def test_combined_score_value_in_range():
    cases = [
        combined_score(_validation(), _match(1.0), None),
        combined_score(_validation(), _match(1.0), 1.0),
        combined_score(_validation(_failure(CheckCode.TOTAL_MISMATCH, Severity.BLOCKER)), _match(0.0), 0.0),
        combined_score(_validation(), _match(0.0), 0.0),
    ]
    for s in cases:
        assert 0.0 <= s.value <= 1.0
