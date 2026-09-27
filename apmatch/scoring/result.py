"""Deterministic confidence score and routing decision.

No I/O. The routing decision and confidence score are enum-coded; the same
input always produces the same output. A ``RoutingDecision`` carries a single
``Route`` + ``RouteReason`` pair, never free text — reviewers read the
underlying ``ValidationResult`` / ``MatchResult`` for detail.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from apmatch.validation.result import Severity  # noqa: F401  (re-exported for callers)


class Route(str, Enum):
    AUTO_APPROVE = "AUTO_APPROVE"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    REJECT = "REJECT"


class RouteReason(str, Enum):
    # reasons AUTO_APPROVE
    ALL_CHECKS_PASSED = "ALL_CHECKS_PASSED"

    # reasons REJECT
    VALIDATION_BLOCKER = "VALIDATION_BLOCKER"

    # reasons HUMAN_REVIEW
    MATCH_DISCREPANCY = "MATCH_DISCREPANCY"
    MATCH_PENDING_INFO = "MATCH_PENDING_INFO"
    LOW_OCR_CONFIDENCE = "LOW_OCR_CONFIDENCE"
    LOW_OVERALL_SCORE = "LOW_OVERALL_SCORE"


@dataclass(frozen=True)
class ConfidenceScore:
    value: float  # in [0.0, 1.0]
    validation_component: float  # in [0.0, 1.0]
    match_component: float  # in [0.0, 1.0]
    ocr_component: float | None  # None if no OCR confidence available

    @property
    def ok(self) -> bool:
        # Convenience threshold; distinct from config.AUTO_APPROVE_SCORE_MIN.
        return self.value >= 0.75


@dataclass(frozen=True)
class RoutingDecision:
    route: Route
    reason: RouteReason
    score: ConfidenceScore
    # Reserved for a future explanation; not free text today. If a reviewer
    # needs details, they read the ValidationResult and MatchResult directly.

    @property
    def is_auto_approve(self) -> bool:
        return self.route is Route.AUTO_APPROVE

    @property
    def needs_human(self) -> bool:
        return self.route is Route.HUMAN_REVIEW
