"""Scoring & routing configuration constants.

Constants, not config files; every change requires a task, rationale, and
updated tests. No environment variables, no config files. The combined score
is a float (matching ``MatchResult.score``), so the weights are floats too.
"""

# Thresholds
AUTO_APPROVE_SCORE_MIN = 0.90  # >= this → eligible for AUTO_APPROVE
REJECT_REQUIRES_BLOCKER = True  # REJECT only when a BLOCKER exists
OCR_CONFIDENCE_LOW = 0.80  # below this → degrade to HUMAN_REVIEW

# Weight of each component in the combined score (must sum to 1.0)
WEIGHT_VALIDATION = 0.30
WEIGHT_MATCH = 0.50
WEIGHT_OCR = 0.20  # only applied when OCR confidence present

# When OCR confidence is not provided, the weights are renormalized over the
# remaining two components (see apmatch.scoring.confidence).

__all__ = [
    "AUTO_APPROVE_SCORE_MIN",
    "OCR_CONFIDENCE_LOW",
    "REJECT_REQUIRES_BLOCKER",
    "WEIGHT_MATCH",
    "WEIGHT_OCR",
    "WEIGHT_VALIDATION",
]
