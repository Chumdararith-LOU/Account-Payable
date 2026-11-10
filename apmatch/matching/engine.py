"""Deterministic 4-way matching engine.

Pure, no I/O, no LLM, no network. Consumes the schema dataclasses
(``Invoice``, ``PurchaseOrder``, ``GRNI``, ``PaymentAdvice``) and produces a
``MatchResult``.

Matching strategy: vendor name via ``vendor_names_match``; currency via
``normalize_currency``; line items joined on ``normalize_text(description)``
with quantity/price/amount tolerance checks.

Line-item matching is two-tier:
  1. Exact match on normalized description (deterministic, no model).
  2. If no exact match AND an ``embedding_model`` was provided to the
     constructor: cosine similarity against each candidate line.
     - best score >= SIMILARITY_ACCEPT (0.70): accept, no failure
     - best score in [SIMILARITY_REVIEW, SIMILARITY_ACCEPT): accept,
       add a SIMILARITY_MATCH_REVIEW warning (routes to human review)
     - best score < SIMILARITY_REVIEW (0.55): no match;
       NO_MATCHING_PO_LINE / NO_MATCHING_GRNI_LINE as before
  Every similarity-based match is recorded as a ``SimilarityMatch`` on the
  result. The engine is fast when constructed without a model.

Currency rule: CURRENCY_MISMATCH fires when invoice.currency and (po.currency
or pard.currency) are both populated and differ after normalize_currency.
Missing currency on either side skips the check — no false positive. PO and
PARD are checked independently, so both can fail at once (two failures).

Score model: starts at 1.0; every ``MatchFailure`` subtracts its weight from
``config.MATCH_CODE_WEIGHTS``; the result is clamped to [0.0, 1.0]. A missing
PO/GRNI/PARD short-circuits to PENDING_INFO with score 0.0 before any further
checks run.

Money quantities come from the schema dataclasses, which guarantee Decimal. If
a caller somehow passes a float, Decimal/float arithmetic raises TypeError at
runtime; we deliberately do NOT cast.
"""

from __future__ import annotations

import dataclasses
import difflib
import json
import re
import sys
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from enum import Enum
from pathlib import Path

from apmatch.embeddings.config import SIMILARITY_ACCEPT, SIMILARITY_REVIEW
from apmatch.matching.config import (
    AMOUNT_TOLERANCE,
    AMOUNT_TOLERANCE_REL,
    MATCH_CODE_WEIGHTS,
    QTY_TOLERANCE_ABS,
    SUPPORTED_CURRENCIES,
    TAX_RATE_MAX,
    TAX_RATE_MIN,
    TAX_TOLERANCE_ABS,
    TAX_TOLERANCE_ABS_KHR,
    TAX_TOLERANCE_REL,
    TOTAL_TOLERANCE,
    UNIT_PRICE_TOLERANCE,
    UNIT_PRICE_TOLERANCE_REL,
)
from apmatch.matching.normalize import (
    normalize_currency,
    normalize_number_text,
    normalize_text,
    vendor_names_match,
)
from apmatch.matching.result import (
    MatchCode,
    MatchFailure,
    MatchResult,
    Outcome,
    SimilarityMatch,
    _order_failures,
)
from apmatch.schema.coercion import to_money, to_qty, to_unit_price
from apmatch.schema.documents import GRNI, Invoice, LineItem, PaymentAdvice, PurchaseOrder
from apmatch.validation.result import Severity


class MatchingEngine:
    """Matches an invoice against its PO, GRNI, and payment advice."""

    def __init__(self, embedding_model=None) -> None:
        # Optional duck-typed embedding model (needs .similarity() and
        # .model_version). None disables the similarity fallback — the
        # engine then behaves exactly as before (fast path for tests and
        # CLI tools). The class is NOT imported here: apmatch.embeddings.model
        # pulls in sentence-transformers, which must stay out of every import
        # path that does not need it (D-082).
        self._embedding_model = embedding_model

    def _similarity_lookup(
        self, inv_line: LineItem, candidates: tuple[LineItem, ...], counterpart: str
    ) -> tuple[LineItem | None, SimilarityMatch | None]:
        """
        Find the candidate line with the highest embedding
        similarity to inv_line.description.

        Returns (candidate_line_or_None, SimilarityMatch_or_None).

        - If the best score is below SIMILARITY_REVIEW:
            returns (None, None) — no match.
        - If the best score is in [REVIEW, ACCEPT):
            returns (candidate, SimilarityMatch(band="review")).
        - If the best score is >= ACCEPT:
            returns (candidate, SimilarityMatch(band="accept")).

        Determinism: ties broken by candidate line_no ascending,
        then by candidate description ascending. Never by dict
        iteration order.
        """
        if not candidates:
            return None, None

        inv_text = normalize_text(inv_line.description)
        if not inv_text:
            return None, None

        # Compute similarity against each candidate. Use the
        # model's .similarity() method (not .encode()) so we
        # get the wrapper's determinism guarantees.
        scores: list[tuple[float, LineItem]] = []
        for cand in candidates:
            cand_text = normalize_text(cand.description)
            if not cand_text:
                continue
            score = self._embedding_model.similarity(inv_text, cand_text)
            scores.append((score, cand))

        if not scores:
            return None, None

        # Sort: descending score, then ascending line_no, then ascending
        # normalized description.
        scores.sort(key=lambda t: (-t[0], t[1].line_no, normalize_text(t[1].description)))

        best_score, best_cand = scores[0]

        # Quantize for the record.
        score_dec = Decimal(str(best_score)).quantize(
            Decimal("0.0001"), rounding=ROUND_HALF_UP
        )

        if score_dec < SIMILARITY_REVIEW:
            return None, None

        band = "accept" if score_dec >= SIMILARITY_ACCEPT else "review"
        sim = SimilarityMatch(
            location=f"line {inv_line.line_no} (INV) -> "
            f"line {best_cand.line_no} ({counterpart})",
            invoice_text=inv_text,
            counterpart_text=normalize_text(best_cand.description),
            score=score_dec,
            threshold_review=SIMILARITY_REVIEW,
            threshold_accept=SIMILARITY_ACCEPT,
            band=band,
            model_version=self._embedding_model.model_version,
        )
        return best_cand, sim

    def match(
        self,
        invoice: Invoice,
        po: PurchaseOrder | None,
        grni: GRNI | None,
        pard: PaymentAdvice | None,
    ) -> MatchResult:
        failures: list[MatchFailure] = []

        # 1. Missing-document short-circuit.
        missing = []
        if po is None:
            missing.append(MatchCode.PO_MISSING)
        if grni is None:
            missing.append(MatchCode.GRNI_MISSING)
        if pard is None:
            missing.append(MatchCode.PARD_MISSING)
        if missing:
            for code in missing:
                failures.append(
                    MatchFailure(code, Severity.BLOCKER, "header", "present", "missing", "")
                )
            return MatchResult(
                outcome=Outcome.PENDING_INFO,
                score=0.0,
                failures=_order_failures(failures),
                invoice_number=invoice.invoice_number,
                po_number=po.po_number if po else None,
                grn_number=grni.grn_number if grni else None,
                pard_ref=pard.pard_number if pard else None,
            )

        # After the short-circuit, all three documents are guaranteed present.
        assert po is not None and grni is not None and pard is not None

        # 2. Header checks.
        # Vendor: same company despite punctuation / legal-form / minor
        # reading differences ("Co., Ltd." vs "Ltd") — see vendor_names_match.
        if not vendor_names_match(invoice.vendor_name, po.vendor_name):
            failures.append(
                MatchFailure(
                    MatchCode.VENDOR_MISMATCH,
                    Severity.WARNING,
                    "header",
                    normalize_text(po.vendor_name),
                    normalize_text(invoice.vendor_name),
                    "",
                )
            )
        # Currency: compare invoice against PO and PARD, but only when both
        # sides are populated. Missing currency on either side skips the check
        # (no false positive). See module docstring.
        inv_cur = normalize_currency(invoice.currency or "")
        po_cur = normalize_currency(po.currency or "")
        if inv_cur and po_cur and inv_cur != po_cur:
            failures.append(
                MatchFailure(
                    MatchCode.CURRENCY_MISMATCH,
                    Severity.BLOCKER,
                    "header (invoice vs PO)",
                    inv_cur,
                    po_cur,
                    "",
                )
            )
        pard_cur = normalize_currency(pard.currency or "")
        # Only USD and KHR are processed (D-115); anything else goes to a human.
        for where, cur in (("invoice", inv_cur), ("PO", po_cur), ("payment advice", pard_cur)):
            if cur and cur not in SUPPORTED_CURRENCIES:
                failures.append(
                    MatchFailure(
                        MatchCode.CURRENCY_UNSUPPORTED,
                        Severity.WARNING,
                        where,
                        "USD or KHR",
                        cur,
                        "",
                    )
                )
        if inv_cur and pard_cur and inv_cur != pard_cur:
            failures.append(
                MatchFailure(
                    MatchCode.CURRENCY_MISMATCH,
                    Severity.BLOCKER,
                    "header (invoice vs PARD)",
                    inv_cur,
                    pard_cur,
                    "",
                )
            )

        # 3. Line-item matching.
        similarity_matches: list[SimilarityMatch] = []
        for n, inv_line in enumerate(invoice.line_items, start=1):
            po_line = _find_line(po.line_items, inv_line.description)
            if po_line is None:
                po_line = _find_close_line(po.line_items, inv_line, against_po=True)
            if po_line is None and self._embedding_model is not None:
                po_line, sim = self._similarity_lookup(inv_line, po.line_items, "PO")
                if sim is not None:
                    similarity_matches.append(sim)
                    if sim.band == "review":
                        failures.append(
                            MatchFailure(
                                MatchCode.SIMILARITY_MATCH_REVIEW,
                                Severity.WARNING,
                                sim.location,
                                sim.counterpart_text,
                                sim.invoice_text,
                                "",
                            )
                        )
            if po_line is None:
                failures.append(
                    MatchFailure(
                        MatchCode.NO_MATCHING_PO_LINE,
                        Severity.WARNING,
                        f"line {n} (INV)",
                        "a PO line",
                        "none",
                        "",
                    )
                )
            else:
                loc = f"line {n} (INV) -> line {po_line.line_no} (PO)"
                # Partial billing is normal: an invoice may bill fewer units
                # than ordered (the GRN check below ties it to what was
                # received). Billing MORE than ordered is a discrepancy.
                if (
                    inv_line.quantity is not None
                    and po_line.quantity is not None
                    and inv_line.quantity - po_line.quantity > QTY_TOLERANCE_ABS
                ):
                    failures.append(
                        MatchFailure(
                            MatchCode.QTY_MISMATCH,
                            Severity.WARNING,
                            loc,
                            str(po_line.quantity),
                            str(inv_line.quantity),
                            str(abs(inv_line.quantity - po_line.quantity)),
                        )
                    )
                if inv_line.unit_price is not None and po_line.unit_price is not None:
                    diff = abs(inv_line.unit_price - po_line.unit_price)
                    max_val = max(abs(inv_line.unit_price), abs(po_line.unit_price))
                    if diff > UNIT_PRICE_TOLERANCE and (
                        max_val == 0 or diff / max_val > UNIT_PRICE_TOLERANCE_REL
                    ):
                        failures.append(
                            MatchFailure(
                                MatchCode.UNIT_PRICE_MISMATCH,
                                Severity.WARNING,
                                loc,
                                str(po_line.unit_price),
                                str(inv_line.unit_price),
                                str(diff),
                            )
                        )
                billed_qty = inv_line.quantity if inv_line.quantity is not None else po_line.quantity
                if (
                    inv_line.amount is not None
                    and billed_qty is not None
                    and po_line.unit_price is not None
                ):
                    # The amount the PO price allows for the quantity billed.
                    po_amount = billed_qty * po_line.unit_price
                    diff = abs(inv_line.amount - po_amount)
                    max_val = max(abs(inv_line.amount), abs(po_amount))
                    if diff > AMOUNT_TOLERANCE and (
                        max_val == 0 or diff / max_val > AMOUNT_TOLERANCE_REL
                    ):
                        failures.append(
                            MatchFailure(
                                MatchCode.LINE_AMOUNT_MISMATCH,
                                Severity.WARNING,
                                loc,
                                str(po_amount),
                                str(inv_line.amount),
                                str(diff),
                            )
                        )

            grni_line = _find_line(grni.line_items, inv_line.description)
            if grni_line is None:
                grni_line = _find_close_line(grni.line_items, inv_line, against_po=False)
            if grni_line is None and self._embedding_model is not None:
                grni_line, sim = self._similarity_lookup(inv_line, grni.line_items, "GRN")
                if sim is not None:
                    similarity_matches.append(sim)
                    if sim.band == "review":
                        failures.append(
                            MatchFailure(
                                MatchCode.SIMILARITY_MATCH_REVIEW,
                                Severity.WARNING,
                                sim.location,
                                sim.counterpart_text,
                                sim.invoice_text,
                                "",
                            )
                        )
            if grni_line is None:
                failures.append(
                    MatchFailure(
                        MatchCode.NO_MATCHING_GRNI_LINE,
                        Severity.WARNING,
                        f"line {n} (INV)",
                        "a GRNI line",
                        "none",
                        "",
                    )
                )
            elif (
                inv_line.quantity is not None
                and grni_line.quantity is not None
                and abs(inv_line.quantity - grni_line.quantity) > QTY_TOLERANCE_ABS
            ):
                failures.append(
                    MatchFailure(
                        MatchCode.QTY_MISMATCH,
                        Severity.WARNING,
                        f"line {n} (INV) -> line {grni_line.line_no} (GRNI)",
                        str(grni_line.quantity),
                        str(inv_line.quantity),
                        str(abs(inv_line.quantity - grni_line.quantity)),
                    )
                )

        # 4. PARD amount vs invoice total. Skip when either side is None —
        # the validator already emits MISSING_REQUIRED_FIELD(blocker) for a
        # missing header field, so the route is REJECT before matching runs.
        if (
            pard.amount is not None
            and invoice.total is not None
            and abs(pard.amount - invoice.total) > TOTAL_TOLERANCE
        ):
            failures.append(
                MatchFailure(
                    MatchCode.PARD_AMOUNT_MISMATCH,
                    Severity.BLOCKER,
                    "header",
                    str(invoice.total),
                    str(pard.amount),
                    str(abs(pard.amount - invoice.total)),
                )
            )

        # 4b. Invoice tax vs the PO's tax rate (D-113).
        tax_failure = _tax_check(invoice, po)
        if tax_failure is not None:
            failures.append(tax_failure)

        # 4c. The invoice must cite the PO it is matched against.
        if po.po_number:
            cited = invoice.po_number
            if not cited or not _refs_agree(cited, po.po_number, invoice, po):
                failures.append(
                    MatchFailure(
                        MatchCode.PO_REFERENCE_MISMATCH,
                        Severity.WARNING,
                        "header (invoice vs PO)",
                        po.po_number,
                        cited or "none",
                        "",
                    )
                )

        # 4d. Goods received after the invoice date: hold for review.
        if (
            grni.grni_date is not None
            and invoice.invoice_date is not None
            and grni.grni_date > invoice.invoice_date
        ):
            failures.append(
                MatchFailure(
                    MatchCode.RECEIVED_AFTER_INVOICE,
                    Severity.WARNING,
                    "header (GRN vs invoice)",
                    str(invoice.invoice_date),
                    str(grni.grni_date),
                    "",
                )
            )

        # 5. Date ordering (soft). Skip when either date is None (same reason).
        if (
            pard.payment_date is not None
            and invoice.invoice_date is not None
            and pard.payment_date < invoice.invoice_date
        ):
            failures.append(
                MatchFailure(
                    MatchCode.DATE_OUT_OF_ORDER,
                    Severity.INFO,
                    "header",
                    str(invoice.invoice_date),
                    str(pard.payment_date),
                    "",
                )
            )

        # 5b. Sequence and reference sanity.
        if (
            invoice.invoice_date is not None
            and po.po_date is not None
            and invoice.invoice_date < po.po_date
        ):
            failures.append(
                MatchFailure(
                    MatchCode.INVOICE_BEFORE_PO,
                    Severity.WARNING,
                    "header (invoice vs PO)",
                    str(po.po_date),
                    str(invoice.invoice_date),
                    "",
                )
            )
        if pard.invoice_number is not None and invoice.invoice_number is not None:
            if normalize_number_text(pard.invoice_number) != normalize_number_text(invoice.invoice_number):
                failures.append(
                    MatchFailure(
                        MatchCode.PARD_INVOICE_MISMATCH,
                        Severity.BLOCKER,
                        "header (PARD vs invoice)",
                        invoice.invoice_number,
                        pard.invoice_number,
                        "",
                    )
                )
        if invoice.duplicate_of_run_id is not None:
            failures.append(
                MatchFailure(
                    MatchCode.DUPLICATE_INVOICE,
                    Severity.BLOCKER,
                    "header",
                    "no prior run",
                    invoice.duplicate_of_run_id,
                    "",
                )
            )

        # 6. Outcome + score. Any failure (blocker or not) is a DISCREPANCY;
        # the blocker distinction is carried by MatchResult.has_blocker.
        outcome = Outcome.DISCREPANCY if failures else Outcome.MATCH
        total_weight = sum((MATCH_CODE_WEIGHTS[f.code] for f in failures), Decimal("0"))
        score = float(max(Decimal("0"), Decimal("1") - total_weight))

        return MatchResult(
            outcome=outcome,
            score=score,
            failures=_order_failures(failures),
            invoice_number=invoice.invoice_number,
            po_number=po.po_number,
            grn_number=grni.grn_number,
            pard_ref=pard.pard_number,
            similarity_matches=tuple(similarity_matches),
        )


_NON_ALNUM_RE = re.compile(r"[\W_]+", re.UNICODE)
_PREFIX_MIN_CHARS = 4
_CLOSE_NAME_MIN = 0.85


def _compact(description: str) -> str:
    return _NON_ALNUM_RE.sub("", normalize_text(description))


def _price_agrees(a: Decimal, b: Decimal) -> bool:
    diff = abs(a - b)
    biggest = max(abs(a), abs(b))
    return diff <= UNIT_PRICE_TOLERANCE or (biggest != 0 and diff / biggest <= UNIT_PRICE_TOLERANCE_REL)


def _names_close(a: str, b: str) -> bool:
    """Same item named a little differently (deterministic, no model):
    - one name starts with the other, ignoring spaces/punctuation, >= 4 chars
      ("UPS 1000VA" vs "UPS1000VA -600W -Line-interactive")
    - same words in another order ("Belt, serpentine" vs "Serpentine belt")
    - a typo-level spelling difference ("Filmaent" vs "Filament", >= 0.85)
    """
    ca, cb = _compact(a), _compact(b)
    if min(len(ca), len(cb)) < _PREFIX_MIN_CHARS:
        return False
    if ca.startswith(cb) or cb.startswith(ca):
        return True
    words_a = sorted(_NON_ALNUM_RE.sub(" ", normalize_text(a)).split())
    words_b = sorted(_NON_ALNUM_RE.sub(" ", normalize_text(b)).split())
    if words_a == words_b:
        return True
    return difflib.SequenceMatcher(None, ca, cb).ratio() >= _CLOSE_NAME_MIN


def names_close(a: str, b: str, *, exact_ok: bool = False) -> bool:
    """Public: the same item (exactly, if ``exact_ok``, or closely named)."""
    if exact_ok and normalize_text(a) == normalize_text(b):
        return True
    return _names_close(a, b)


def _find_close_line(
    lines: tuple[LineItem, ...], inv_line: LineItem, *, against_po: bool
) -> LineItem | None:
    """Tier 2 line join, after exact and before embeddings (D-113).

    Matches when the names are close (``_names_close``) AND the numbers
    agree: for a PO line the unit price is within tolerance and the invoice
    does not bill more than ordered; for a GRN line the quantity is equal.
    Requiring the numbers keeps "Office Chair" from matching an unrelated
    "Office Chair Mat". First match in source order.
    """
    for line in lines:
        if not _names_close(inv_line.description, line.description):
            continue
        if against_po:
            if inv_line.unit_price is None or line.unit_price is None:
                continue
            if not _price_agrees(inv_line.unit_price, line.unit_price):
                continue
            if inv_line.quantity is not None and line.quantity is not None and inv_line.quantity > line.quantity:
                continue
        elif inv_line.quantity is None or line.quantity is None or inv_line.quantity != line.quantity:
            continue
        return line
    return None


def _ref_key(number: str) -> str:
    """Document number for comparison: letters and digits only, uppercased."""
    return _NON_ALNUM_RE.sub("", normalize_number_text(number))


def _refs_agree(cited: str, po_number: str, invoice: Invoice, po: PurchaseOrder) -> bool:
    """Same PO reference. One differing character ("3878" vs "3876") is taken
    as a misread only when the invoice total equals the PO total to the cent."""
    a, b = _ref_key(cited), _ref_key(po_number)
    if a == b:
        return True
    one_off = len(a) == len(b) and sum(x != y for x, y in zip(a, b, strict=True)) == 1
    return (
        one_off
        and invoice.total is not None
        and po.total is not None
        and abs(invoice.total - po.total) <= TOTAL_TOLERANCE
    )


def _line_value(line: LineItem) -> Decimal | None:
    if line.amount is not None:
        return line.amount
    if line.quantity is not None and line.unit_price is not None:
        return line.quantity * line.unit_price
    return None


def _tax_check(invoice: Invoice, po: PurchaseOrder) -> MatchFailure | None:
    """Invoice tax vs the rate implied by the PO (PO total / PO lines - 1).

    Skipped when an input is missing or the implied rate is not a plausible
    tax rate (e.g. the PO total excludes tax).
    """
    if po.total is None or invoice.subtotal is None or invoice.tax_amount is None:
        return None
    values = [_line_value(li) for li in po.line_items]
    if not values or any(v is None for v in values):
        return None
    base = sum(values, Decimal("0"))
    if base <= 0:
        return None
    rate = po.total / base - 1
    if not (TAX_RATE_MIN <= rate <= TAX_RATE_MAX):
        return None
    discount = invoice.discount_amount if invoice.discount_amount is not None else Decimal("0")
    expected = (invoice.subtotal - discount) * rate
    abs_tol = TAX_TOLERANCE_ABS_KHR if normalize_currency(invoice.currency or "") == "KHR" else TAX_TOLERANCE_ABS
    tolerance = max(abs_tol, abs(expected) * TAX_TOLERANCE_REL)
    diff = abs(invoice.tax_amount - expected)
    if diff <= tolerance:
        return None
    return MatchFailure(
        MatchCode.TAX_MISMATCH,
        Severity.WARNING,
        "header (invoice vs PO)",
        str(to_money(expected)),
        str(invoice.tax_amount),
        str(to_money(diff)),
    )


def _find_line(lines: tuple[LineItem, ...], description: str) -> LineItem | None:
    """Return the FIRST line (source order) whose normalized description matches."""
    target = normalize_text(description)
    for line in lines:
        if normalize_text(line.description) == target:
            return line
    return None


# --- CLI -------------------------------------------------------------------


def _build_line(li: dict, default_no: int) -> LineItem:
    return LineItem(
        line_no=li.get("line_no", default_no),
        description=li["description"],
        quantity=to_qty(li["quantity"]),
        unit_price=to_unit_price(li["unit_price"]) if li.get("unit_price") is not None else None,
        amount=to_money(li["amount"]) if li.get("amount") is not None else None,
        unit_of_measure=li.get("unit_of_measure"),
    )


def _build_invoice(d: dict) -> Invoice:
    return Invoice(
        invoice_number=d["invoice_number"],
        vendor_name=d["vendor_name"],
        invoice_date=date.fromisoformat(d["invoice_date"]),
        currency=d["currency"],
        subtotal=to_money(d["subtotal"]),
        tax_amount=to_money(d["tax_amount"]),
        total=to_money(d["total"]),
        line_items=tuple(_build_line(li, i + 1) for i, li in enumerate(d.get("line_items", []))),
        po_number=d.get("po_number"),
        grn_number=d.get("grn_number"),
        discount_amount=to_money(d["discount_amount"]) if d.get("discount_amount") is not None else None,
    )


def _build_po(d: dict) -> PurchaseOrder:
    return PurchaseOrder(
        po_number=d["po_number"],
        vendor_name=d["vendor_name"],
        po_date=date.fromisoformat(d["po_date"]),
        total=to_money(d["total"]),
        line_items=tuple(_build_line(li, i + 1) for i, li in enumerate(d.get("line_items", []))),
    )


def _build_grni(d: dict) -> GRNI:
    return GRNI(
        grn_number=d["grn_number"],
        vendor_name=d["vendor_name"],
        grni_date=date.fromisoformat(d["grni_date"]),
        line_items=tuple(_build_line(li, i + 1) for i, li in enumerate(d.get("line_items", []))),
    )


def _build_pard(d: dict) -> PaymentAdvice:
    return PaymentAdvice(
        pard_number=d["pard_number"],
        invoice_number=d["invoice_number"],
        amount=to_money(d["amount"]),
        payment_date=date.fromisoformat(d["payment_date"]),
        reference=d.get("reference"),
    )


def _enum_to_value(obj):
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, dict):
        return {k: _enum_to_value(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_enum_to_value(v) for v in obj]
    return obj


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: python -m apmatch.matching.engine <json_dir>", file=sys.stderr)
        return 2
    root = Path(argv[0])
    invoice = _build_invoice(json.loads((root / "invoice.json").read_text(encoding="utf-8")))
    po = _build_po(json.loads((root / "po.json").read_text(encoding="utf-8")))
    grni = _build_grni(json.loads((root / "grni.json").read_text(encoding="utf-8")))
    pard = _build_pard(json.loads((root / "pard.json").read_text(encoding="utf-8")))
    result = MatchingEngine().match(invoice, po, grni, pard)
    print(json.dumps(_enum_to_value(dataclasses.asdict(result)), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
