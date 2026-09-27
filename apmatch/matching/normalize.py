"""Pure text-normalization functions for matching.

Pure functions, no I/O, no state. Deterministic: the same input always produces
the same output, byte-for-byte. The OCR-noise stripping is a heuristic; when in
doubt it errs on the side of KEEPING content — a false positive that leaks noise
is less harmful than a false negative that destroys meaning.
"""

from __future__ import annotations

import re
import unicodedata

# A slash followed by 1-8 lowercase ASCII letters at a word boundary. Targets
# observed OCR noise like "/nnw", "/uww", "/ujwnw" WITHOUT touching legitimate
# slashes followed by uppercase ("P/N 12345") or digits ("1/2 inch").
_OCR_SUFFIX_RE = re.compile(r"/[a-z]{1,8}\b")
_WS_RE = re.compile(r"\s+")


def _strip_ocr_suffix(s: str) -> str:
    """Remove OCR noise suffixes (slash + 1-8 lowercase letters + word boundary)."""
    return _OCR_SUFFIX_RE.sub("", s)


def normalize_text(s: str) -> str:
    """Canonicalize a description/name for comparison.

    Steps (in order):
      1. Unicode NFKC normalize.
      2. Replace any Unicode whitespace (tabs, NBSP, ...) with ASCII space.
      3. Strip OCR noise suffixes (``/[a-z]{1,8}\\b``).
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
