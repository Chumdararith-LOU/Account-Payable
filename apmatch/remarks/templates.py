"""Deterministic, template-based reviewer remarks.

This module is the deterministic replacement for the removed LLM (D-005). It
turns a ``ValidationResult`` into a one-line, plain-language remark for the
human reviewer.

Guarantees (provable by inspection):
- Deterministic: no LLM, no network, no randomness, no time-dependent text.
  The same ``CheckFailure`` always produces the same string; the same
  ``ValidationResult`` always produces byte-identical output.
- Every ``CheckCode`` maps to exactly one template in ``TEMPLATES``. Adding a
  new ``CheckCode`` requires adding a template here; the import-time assertion
  below (and ``tests/remarks/test_templates.py``) fail loudly if a code has no
  template. Silent fallbacks are forbidden — they are how LLMs sneak back in.
- English-only for now. Khmer i18n is deferred to P1-13; the public functions
  take a ``lang: str = "en"`` parameter that is currently ignored (reserved).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from apmatch.validation.result import CheckCode, CheckFailure, Severity, ValidationResult

LOCALE_DEFAULT = "en"

# One template per CheckCode. Placeholders: {expected} {actual} {delta}
# {location} {code}. Every template is a single sentence ending in a period.
TEMPLATES: dict[CheckCode, str] = {
    CheckCode.LINE_AMOUNT_MISMATCH: (
        "Line {location} amount mismatch: expected {expected}, actual {actual} (off by {delta})."
    ),
    CheckCode.SUBTOTAL_MISMATCH: "Subtotal mismatch: expected {expected}, actual {actual} (off by {delta}).",
    CheckCode.TAX_MISMATCH: "Tax mismatch: expected {expected}, actual {actual} (off by {delta}).",
    CheckCode.DISCOUNT_MISMATCH: "Discount mismatch: expected {expected}, actual {actual} (off by {delta}).",
    CheckCode.TOTAL_MISMATCH: "Total mismatch: expected {expected}, actual {actual} (off by {delta}).",
    CheckCode.MISSING_REQUIRED_FIELD: "Missing required field at {location}: {actual}.",
    CheckCode.NEGATIVE_AMOUNT: "Negative amount at {location}: {actual}.",
    CheckCode.NO_LINE_ITEMS: "No line items present.",
    CheckCode.DATE_IN_FUTURE: "Document date is in the future: {actual}.",
    CheckCode.CURRENCY_MISMATCH: "Currency mismatch: expected {expected}, actual {actual}.",
}


def _assert_all_codes_covered() -> None:
    missing = [c for c in CheckCode if c not in TEMPLATES]
    if missing:
        raise RuntimeError(f"CheckCode(s) without a remark template: {[c.value for c in missing]}")


# Fail loudly at import time if a CheckCode lacks a template.
_assert_all_codes_covered()


def remark_for(failure: CheckFailure, lang: str = LOCALE_DEFAULT) -> str:
    """Render one ``CheckFailure`` to its remark string.

    Pure. Raises ``KeyError`` if the failure's code has no template (the
    import-time check makes this unreachable in practice).
    """
    template = TEMPLATES[failure.code]
    return template.format(
        expected=failure.expected,
        actual=failure.actual,
        delta=failure.delta,
        location=failure.location,
        code=failure.code.value,
    )


def summarize(result: ValidationResult, lang: str = LOCALE_DEFAULT) -> str:
    """Render a whole ``ValidationResult`` to a one-line remark.

    Contract:
    - No failures            -> "Validated OK."
    - Exactly one failure    -> that failure's remark.
    - More than one failure  -> "<n> issue(s). Most severe: <first failure's
      remark>", where the first failure is ``checks_failed[0]`` (the result is
      already ordered by severity desc per the P1-06 contract).

    Pure. No I/O, no logging, no state.
    """
    if not result.checks_failed:
        return "Validated OK."
    if len(result.checks_failed) == 1:
        return remark_for(result.checks_failed[0], lang)
    return f"{len(result.checks_failed)} issue(s). Most severe: {remark_for(result.checks_failed[0], lang)}"


def _result_from_dict(d: dict) -> ValidationResult:
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


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: python -m apmatch.remarks.templates <json_path>", file=sys.stderr)
        return 2
    data = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    print(summarize(_result_from_dict(data)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
