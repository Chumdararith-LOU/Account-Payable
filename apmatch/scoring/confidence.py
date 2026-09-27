"""Pure confidence-score computation.

No I/O, no LLM, no network. Deterministic: the same inputs always produce the
same ``ConfidenceScore``. The severity penalties in ``validation_component``
express the meaning of a severity level, so they live here, not in config.
"""

from __future__ import annotations

from apmatch.matching.result import MatchResult
from apmatch.scoring.config import WEIGHT_MATCH, WEIGHT_OCR, WEIGHT_VALIDATION
from apmatch.scoring.result import ConfidenceScore
from apmatch.validation.result import Severity, ValidationResult

# How much each failure severity dents the validation component. These express
# the meaning of severity, so they belong to this function, not to config.
_BLOCKER_PENALTY = 0.5
_WARNING_PENALTY = 0.2
_INFO_PENALTY = 0.05


def validation_component(result: ValidationResult) -> float:
    """Score a ``ValidationResult`` in [0, 1]: 1.0 minus a penalty per failure.

    BLOCKER -0.5, WARNING -0.2, INFO -0.05; clamped to [0.0, 1.0].
    """
    score = 1.0
    for failure in result.checks_failed:
        if failure.severity is Severity.BLOCKER:
            score -= _BLOCKER_PENALTY
        elif failure.severity is Severity.WARNING:
            score -= _WARNING_PENALTY
        elif failure.severity is Severity.INFO:
            score -= _INFO_PENALTY
    return max(0.0, min(1.0, score))


def match_component(result: MatchResult) -> float:
    """Reuse ``MatchResult.score`` directly.

    The matching engine already computes a bounded deterministic score; the
    confidence layer does not second-guess it.
    """
    return result.score


def combined_score(
    validation: ValidationResult,
    match: MatchResult,
    ocr_confidence: float | None = None,
) -> ConfidenceScore:
    """Combine the three components into a weighted ``ConfidenceScore``.

    When ``ocr_confidence`` is None, the validation/match weights are
    renormalized to sum to 1.0 and ``ocr_component`` is None. Otherwise all
    three configured weights are used and ``ocr_confidence`` must be in [0, 1]
    (else ``ValueError``).
    """
    v = validation_component(validation)
    m = match_component(match)
    if ocr_confidence is None:
        total = WEIGHT_VALIDATION + WEIGHT_MATCH
        value = (WEIGHT_VALIDATION / total) * v + (WEIGHT_MATCH / total) * m
        ocr = None
    else:
        if not 0.0 <= ocr_confidence <= 1.0:
            raise ValueError(f"ocr_confidence must be in [0, 1], got {ocr_confidence}")
        value = WEIGHT_VALIDATION * v + WEIGHT_MATCH * m + WEIGHT_OCR * ocr_confidence
        ocr = ocr_confidence
    return ConfidenceScore(
        value=value,
        validation_component=v,
        match_component=m,
        ocr_component=ocr,
    )
