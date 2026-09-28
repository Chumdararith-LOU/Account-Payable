"""Deterministic routing decision.

No I/O, no LLM, no network. Consumes a ``ValidationResult`` and ``MatchResult``
(and an optional OCR confidence) and produces a ``RoutingDecision``. The
decision order is fixed and part of the contract: REJECT (validation blocker)
first, then the HUMAN_REVIEW branches, then AUTO_APPROVE.

CLI:
    python -m apmatch.scoring.router <match_result.json> [<validation_result.json>] [--ocr=0.92]

Reads the matching CLI's JSON (required) and optionally the validation CLI's
JSON. When the validation JSON is omitted, an empty (passing) ``ValidationResult``
is assumed. ``--ocr=X`` supplies an OCR confidence in [0, 1]. Prints the
``RoutingDecision`` as JSON (Enum -> ``.value``). Exit 0 — the route is data,
not a status code.
"""

from __future__ import annotations

import dataclasses
import json
import sys
from enum import Enum
from pathlib import Path

from apmatch.matching.result import MatchCode, MatchFailure, MatchResult, Outcome
from apmatch.scoring.confidence import combined_score
from apmatch.scoring.config import (
    AUTO_APPROVE_SCORE_MIN,
    OCR_CONFIDENCE_LOW,
    REJECT_REQUIRES_BLOCKER,
)
from apmatch.scoring.result import Route, RouteReason, RoutingDecision
from apmatch.validation.result import CheckCode, CheckFailure, Severity, ValidationResult


def decide(
    validation: ValidationResult,
    match: MatchResult,
    ocr_confidence: float | None = None,
) -> RoutingDecision:
    """Route a (validation, match, ocr_confidence) triple. Deterministic."""
    # 1. A validation BLOCKER always rejects, regardless of the match.
    if REJECT_REQUIRES_BLOCKER and validation.has_blocker:
        score = combined_score(validation, match, ocr_confidence)
        return RoutingDecision(Route.REJECT, RouteReason.VALIDATION_BLOCKER, score)

    # 2. Compute the combined score once.
    score = combined_score(validation, match, ocr_confidence)

    # 3. Missing documents need a human.
    if match.outcome is Outcome.PENDING_INFO:
        return RoutingDecision(Route.HUMAN_REVIEW, RouteReason.MATCH_PENDING_INFO, score)

    # 4. A discrepancy needs a human.
    if match.outcome is Outcome.DISCREPANCY:
        return RoutingDecision(Route.HUMAN_REVIEW, RouteReason.MATCH_DISCREPANCY, score)

    # 5. Low OCR confidence needs a human.
    if ocr_confidence is not None and ocr_confidence < OCR_CONFIDENCE_LOW:
        return RoutingDecision(Route.HUMAN_REVIEW, RouteReason.LOW_OCR_CONFIDENCE, score)

    # 6. A low overall score needs a human.
    if score.value < AUTO_APPROVE_SCORE_MIN:
        return RoutingDecision(Route.HUMAN_REVIEW, RouteReason.LOW_OVERALL_SCORE, score)

    # 7. Otherwise, auto-approve.
    return RoutingDecision(Route.AUTO_APPROVE, RouteReason.ALL_CHECKS_PASSED, score)


# --- CLI -------------------------------------------------------------------


def _match_from_dict(d: dict) -> MatchResult:
    failures = tuple(
        MatchFailure(
            code=MatchCode(f["code"]),
            severity=Severity(f["severity"]),
            location=f["location"],
            expected=f["expected"],
            actual=f["actual"],
            delta=f["delta"],
        )
        for f in d.get("failures", [])
    )
    return MatchResult(
        outcome=Outcome(d["outcome"]),
        score=float(d["score"]),
        failures=failures,
        invoice_number=d.get("invoice_number", ""),
        po_number=d.get("po_number"),
        grn_number=d.get("grn_number"),
        pard_ref=d.get("pard_ref"),
    )


def _validation_from_dict(d: dict) -> ValidationResult:
    failures = tuple(
        CheckFailure(
            code=CheckCode(f["code"]),
            severity=Severity(f["severity"]),
            location=f["location"],
            expected=f["expected"],
            actual=f["actual"],
            delta=f["delta"],
        )
        for f in d.get("checks_failed", [])
    )
    passed = tuple(CheckCode(c) for c in d.get("checks_passed", []))
    return ValidationResult(
        document_kind=d.get("document_kind", ""),
        checks_passed=passed,
        checks_failed=failures,
    )


def _enum_to_value(obj):
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, dict):
        return {k: _enum_to_value(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_enum_to_value(v) for v in obj]
    return obj


def _parse_args(argv: list[str]):
    ocr = None
    paths: list[str] = []
    for arg in argv:
        if arg.startswith("--ocr="):
            ocr = float(arg.split("=", 1)[1])
        else:
            paths.append(arg)
    return paths, ocr


def main(argv: list[str]) -> int:
    paths, ocr = _parse_args(argv)
    if not paths or len(paths) > 2:
        print(
            "usage: python -m apmatch.scoring.router <match_result.json> "
            "[<validation_result.json>] [--ocr=0.92]",
            file=sys.stderr,
        )
        return 2
    match = _match_from_dict(json.loads(Path(paths[0]).read_text(encoding="utf-8")))
    if len(paths) == 2:
        validation = _validation_from_dict(json.loads(Path(paths[1]).read_text(encoding="utf-8")))
    else:
        validation = ValidationResult(document_kind="", checks_passed=(), checks_failed=())
    decision = decide(validation, match, ocr)
    print(json.dumps(_enum_to_value(dataclasses.asdict(decision)), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
