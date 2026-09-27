"""Deterministic, template-based remarks for match failures.

Parallel to ``apmatch/remarks/templates.py`` (P1-07), but for the matching
engine's ``MatchResult`` instead of a ``ValidationResult``.

Guarantees (provable by inspection):
- Deterministic: no LLM, no network, no randomness, no time-dependent text.
  The same ``MatchFailure`` always produces the same string; the same
  ``MatchResult`` always produces byte-identical output.
- Every ``MatchCode`` maps to exactly one template in ``MATCH_TEMPLATES``.
  Adding a new ``MatchCode`` requires adding a template here; the import-time
  assertion below (and ``tests/remarks/test_matching_templates.py``) fail
  loudly if a code has no template. Silent fallbacks are forbidden — they are
  how LLMs sneak back in.
- English-only for now. Khmer i18n is deferred to P1-13; the public functions
  take a ``lang: str = "en"`` parameter that is currently ignored (reserved).

CLI:
    python -m apmatch.remarks.matching <json_path>

Reads a ``MatchResult`` JSON (``dataclasses.asdict`` output with Enum ->
``.value``, as produced by ``python -m apmatch.matching.engine``), reconstructs
the ``MatchResult``, and prints ``summarize_match()``. Because
``dataclasses.asdict`` does not round-trip enums, the reconstruction converts
the ``.value`` strings back to ``Outcome`` / ``MatchCode`` / ``Severity``
members.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from apmatch.matching.result import MatchCode, MatchFailure, MatchResult, Outcome
from apmatch.validation.result import Severity

LOCALE_DEFAULT = "en"

# One template per MatchCode. Placeholders: {expected} {actual} {delta}
# {location} {code}. Every template is a single sentence ending in a period.
MATCH_TEMPLATES: dict[MatchCode, str] = {
    MatchCode.PO_MISSING: "Purchase order not found.",
    MatchCode.GRNI_MISSING: "Goods received note not found.",
    MatchCode.PARD_MISSING: "Payment advice not found.",
    MatchCode.VENDOR_MISMATCH: "Vendor mismatch: {expected} vs {actual}.",
    MatchCode.CURRENCY_MISMATCH: "Currency mismatch: {expected} vs {actual}.",
    MatchCode.NO_MATCHING_PO_LINE: "No matching PO line for {location}.",
    MatchCode.NO_MATCHING_GRNI_LINE: "No matching GRN line for {location}.",
    MatchCode.QTY_MISMATCH: "Quantity mismatch at {location}: expected {expected}, actual {actual}.",
    MatchCode.UNIT_PRICE_MISMATCH: (
        "Unit price mismatch at {location}: expected {expected}, actual {actual} (off by {delta})."
    ),
    MatchCode.LINE_AMOUNT_MISMATCH: (
        "Line amount mismatch at {location}: expected {expected}, actual {actual} (off by {delta})."
    ),
    MatchCode.PARD_AMOUNT_MISMATCH: (
        "Payment advice amount mismatch: expected {expected}, actual {actual} (off by {delta})."
    ),
    MatchCode.DATE_OUT_OF_ORDER: "Payment advice date precedes invoice date.",
}


def _assert_all_match_codes_covered() -> None:
    missing = [c for c in MatchCode if c not in MATCH_TEMPLATES]
    if missing:
        raise RuntimeError(f"MatchCode(s) without a remark template: {[c.value for c in missing]}")


# Fail loudly at import time if a MatchCode lacks a template.
_assert_all_match_codes_covered()


def remark_for_match(failure: MatchFailure, lang: str = LOCALE_DEFAULT) -> str:
    """Render one ``MatchFailure`` to its remark string.

    Pure. Raises ``KeyError`` if the failure's code has no template (the
    import-time check makes this unreachable in practice).
    """
    if failure.code not in MATCH_TEMPLATES:
        raise KeyError(failure.code)
    template = MATCH_TEMPLATES[failure.code]
    return template.format(
        expected=failure.expected,
        actual=failure.actual,
        delta=failure.delta,
        location=failure.location,
        code=failure.code.value,
    )


def summarize_match(result: MatchResult, lang: str = LOCALE_DEFAULT) -> str:
    """Render a whole ``MatchResult`` to a one-line remark.

    Contract:
    - ``Outcome.MATCH``        -> "All documents match."
    - ``Outcome.PENDING_INFO`` -> "Awaiting information: <first failure's
      remark>", where the first failure is ``failures[0]`` (already ordered by
      severity desc per the P1-08b contract).
    - ``Outcome.DISCREPANCY``  -> exactly one failure: that failure's remark;
      more than one: "<n> issue(s). Most severe: <first failure's remark>".

    Pure. No I/O, no logging, no state.
    """
    if result.outcome is Outcome.MATCH:
        return "All documents match."
    if result.outcome is Outcome.PENDING_INFO:
        return f"Awaiting information: {remark_for_match(result.failures[0], lang)}"
    if len(result.failures) == 1:
        return remark_for_match(result.failures[0], lang)
    return f"{len(result.failures)} issue(s). Most severe: {remark_for_match(result.failures[0], lang)}"


def _result_from_dict(d: dict) -> MatchResult:
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


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: python -m apmatch.remarks.matching <json_path>", file=sys.stderr)
        return 2
    data = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    print(summarize_match(_result_from_dict(data)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
