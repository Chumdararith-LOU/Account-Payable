"""Pure text-normalization functions for matching.

Pure functions, no I/O, no state. Deterministic: the same input always produces
the same output, byte-for-byte. The OCR-noise stripping is a heuristic; when in
doubt it errs on the side of KEEPING content — a false positive that leaks noise
is less harmful than a false negative that destroys meaning.

The OCR-noise regex has two alternatives: letter runs starting lowercase
(1-8 chars, any case mix) and runs starting uppercase (2-8 chars). A trailing
slash with an empty letter run is also stripped. This catches observed OCR
noise like '/Hni', '/nHnw' and 'Desk Lamp/' while preserving part-number
patterns like 'P/N 12345'.
"""

from __future__ import annotations

import difflib
import re
import unicodedata

# A slash followed by a short letter run at a word boundary. Two alternatives:
# runs starting lowercase (1-8 chars, any case mix) and runs starting
# uppercase (2-8 chars). Targets observed OCR noise like "/nnw", "/uww",
# "/ujwnw", "/Hni", "/nHnw" WITHOUT touching legitimate slashes followed by
# a single uppercase letter ("P/N 12345"), digits ("1/2 inch"), or letter
# runs that continue into digits ("Part/AB123" — no word boundary between
# letter and digit).
_OCR_SUFFIX_RE = re.compile(r"/(?:[a-z][a-zA-Z]{0,7}|[A-Z][a-zA-Z]{1,7})\b")
# A trailing slash with an empty letter run: the OCR noise token was cut off
# after the slash ("Desk Lamp/"). No semantic content ends a description.
_OCR_TRAILING_SLASH_RE = re.compile(r"/\s*$")
_WS_RE = re.compile(r"\s+")


def _strip_ocr_suffix(s: str) -> str:
    """Remove OCR noise suffixes (slash + short letter run + word boundary).

    Strips letter runs of 1-8 letters that start lowercase (any case mix)
    and runs of 2-8 letters that start uppercase, plus a trailing slash with
    an empty letter run. Keeps single-uppercase suffixes (P/N), digit
    suffixes (1/2), and runs that continue into digits (Part/AB123).
    """
    s = _OCR_SUFFIX_RE.sub("", s)
    return _OCR_TRAILING_SLASH_RE.sub("", s)


def normalize_text(s: str) -> str:
    """Canonicalize a description/name for comparison.

    Steps (in order):
      1. Unicode NFKC normalize.
      2. Replace any Unicode whitespace (tabs, NBSP, ...) with ASCII space.
      3. Strip OCR noise suffixes (``/(?:[a-z][a-zA-Z]{0,7}|[A-Z][a-zA-Z]{1,7})\\b``
         and a trailing ``/`` with an empty letter run).
      4. Collapse consecutive spaces to a single space.
      5. Strip leading/trailing whitespace.
      6. Casefold.
    """
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", s)
    s = _WS_RE.sub(" ", s)
    s = _strip_ocr_suffix(s)
    s = _WS_RE.sub(" ", s)
    s = s.strip()
    return s.casefold()


def normalize_number_text(s: str) -> str:
    """Canonicalize a document number for comparison.

    Steps: NFKC normalize, remove all whitespace, uppercase. Deliberately does
    NOT strip prefix decorations (e.g. "INV-", "PO-"); callers handle prefix
    logic so this stays a single, predictable transformation.
    """
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", s)
    s = _WS_RE.sub("", s)
    return s.upper()


def normalize_currency(s: str) -> str:
    """Canonicalize an ISO-4217 currency code.

    Strip, uppercase; return "" unless the result is exactly three uppercase
    letters.
    """
    s = s.strip().upper()
    if re.fullmatch(r"[A-Z]{3}", s):
        return s
    return ""


# --- Company names ----------------------------------------------------------

# Legal-form and filler tokens that do not identify a company. Removed before
# comparing vendor names, so "Mekong Supplies Co., Ltd." == "MEKONG SUPPLIES LTD".
_LEGAL_TOKENS = frozenset({
    "co", "company", "ltd", "limited", "llc", "llp", "inc", "incorporated", "corp",
    "corporation", "plc", "pvt", "private", "pte", "gmbh", "sa", "sarl", "the",
})
_NON_WORD_RE = re.compile(r"[^\w]+", re.UNICODE)

# Character-level similarity above which two normalized company names are the
# same company read with minor OCR/VLM noise ("Suplies" vs "Supplies").
COMPANY_SIMILARITY_MIN = 0.92


def normalize_company(s: str | None) -> str:
    """Canonical company name: casefold, punctuation-free, legal forms dropped."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", s).casefold().replace("&", " and ")
    s = _strip_ocr_suffix(s)
    tokens = [t for t in _NON_WORD_RE.sub(" ", s).split() if t not in _LEGAL_TOKENS]
    return " ".join(tokens)


def vendor_names_match(a: str | None, b: str | None) -> bool:
    """True when two vendor names identify the same company.

    Deterministic. Same company when, after ``normalize_company``: the strings
    are equal; or one name's tokens are all contained in the other's and the
    shorter has at least two tokens ("Bayon Office Solutions" vs "Bayon Office
    Solutions Cambodia"); or their character similarity is at least
    COMPANY_SIMILARITY_MIN. Two empty names match (nothing to compare); one
    empty name does not.
    """
    na, nb = normalize_company(a), normalize_company(b)
    if na == nb:
        return True
    if not na or not nb:
        return False
    ta, tb = set(na.split()), set(nb.split())
    small, big = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    if len(small) >= 2 and small <= big:
        return True
    return difflib.SequenceMatcher(None, na, nb).ratio() >= COMPANY_SIMILARITY_MIN
