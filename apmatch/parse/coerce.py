"""Field coercion for noisy OCR strings.

Pure, deterministic functions that wrap P1-06's coercion to handle the noisy
strings OCR actually produces. Every function accepts a string (or None) and
returns a typed value or None — never raises for unconvertible input. The
caller (extractor / validator) decides whether a None is a missing field.
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

logger = logging.getLogger(__name__)

# 3-letter ISO 4217 codes we expect in this corpus.
_ISO_CURRENCY = re.compile(r"\b([A-Z]{3})\b")
_KNOWN_CURRENCIES = {"USD", "KHR", "THB", "VND", "CNY", "EUR", "GBP", "JPY"}


def parse_money(s: str | None) -> Decimal | None:
    """Parse a money string into a Decimal.

    Handles "$1,000.00", "USD 1,000.00", "1,000.00", "1000". Rejects the
    ambiguous European format "1.000,00" (returns None, logs a warning) rather
    than silently mis-parsing it. Returns None on any failure.
    """
    if s is None:
        return None
    text = s.strip()
    if not text:
        return None
    # Strip a leading currency code / symbol.
    text = re.sub(r"^(USD|KHR|THB|VND|CNY|EUR|GBP|JPY|INR)\s*", "", text, flags=re.IGNORECASE)
    text = text.replace("$", "").replace("₹", "").replace("៛", "").strip()
    text = re.sub(r"^Rs\.?\s*", "", text, flags=re.IGNORECASE)
    # Trailing currency code, e.g. "1,036,000.00 KHR" — without this, the
    # "KHR" tail survives into Decimal() and the parse returns None.
    text = re.sub(r"\s*(USD|KHR|THB|VND|CNY|EUR|GBP|JPY|INR)\s*$", "", text, flags=re.IGNORECASE).strip()
    # Space used as a thousands separator ("1 036 000"). Very common when OCR
    # splits a KHR amount across blocks. Only collapse when the pattern is
    # unambiguous: every space is between digit groups of 3.
    if re.fullmatch(r"\d{1,3}(\s\d{3})+", text):
        text = text.replace(" ", "")
    # Ambiguous European format: a dot used as thousands separator followed by
    # a comma decimal (e.g. "1.000,00"). Reject rather than guess.
    if re.fullmatch(r"\d{1,3}(\.\d{3})+,\d{2}", text):
        logger.warning("parse_money: rejecting ambiguous European format %r", s)
        return None
    # Strip thousands separators (commas) that are NOT decimal points.
    if "," in text and "." in text:
        # comma after the last dot -> comma is the decimal separator (European).
        if text.rfind(",") > text.rfind("."):
            logger.warning("parse_money: rejecting ambiguous decimal format %r", s)
            return None
        text = text.replace(",", "")
    elif "," in text:
        # Commas only: valid as 3-digit thousands groups ("1,036,000" — the
        # KHR convention, no decimals). Anything else ("1,23", "12,34,567")
        # is ambiguous -> reject. Trailing OCR noise after a well-formed
        # thousands number ("13,595,000 s") is tolerated.
        m = re.fullmatch(r"\d{1,3}(,\d{3})*", text) or re.match(r"\d{1,3}(,\d{3})+", text)
        if m:
            text = m.group(0).replace(",", "")
        else:
            logger.warning("parse_money: cannot disambiguate comma in %r", s)
            return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def parse_qty(s: str | None) -> Decimal | None:
    """Parse a quantity string into a Decimal.

    Handles "10", "10.0", "10 pcs" (extracts the numeric prefix), "1,000".
    Returns None on failure.
    """
    if s is None:
        return None
    text = s.strip()
    if not text:
        return None
    m = re.search(r"\d[\d,]*(?:\.\d+)?", text)
    if not m:
        return None
    num = m.group(0).replace(",", "")
    try:
        return Decimal(num)
    except InvalidOperation:
        return None


def parse_date(s: str | None, formats: tuple[str, ...] | None = None) -> date | None:
    """Parse a date string into a date.

    Default formats, tried in order:
      "%d-%b-%y"   (17-Dec-25 — 2-digit year; kh_sme invoices)
      "%d-%b-%Y"   (15-Aug-2026 — the legacy format, unambiguous)
      "%Y-%m-%d"   (2026-08-15)
      "%d/%m/%Y"   (15/08/2026)
      "%m/%d/%Y"   (08/15/2026)

    %d-%b-%y is tried before %d-%b-%Y: strptime's %Y rejects 2-digit years,
    and %y fails on 4-digit years (unconverted data), so each form only
    accepts its own. Ambiguity resolution: for slash dates, DD/MM is tried
    before MM/DD. The AP corpus in Cambodia and the region is DD/MM, and the
    legacy DB used the unambiguous %d-%b-%Y. So "03/04/2026" parses as 3
    April 2026, not 4 March. Returns None on failure.
    """
    if s is None:
        return None
    text = s.strip()
    if not text:
        return None
    if formats is None:
        formats = ("%d-%b-%y", "%d-%b-%Y", "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y")
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def parse_document_number(s: str | None) -> str | None:
    """Clean a document number.

    Strips trailing punctuation, preserves the prefix (INV-, PO-, GRN-, PARD-),
    strips internal whitespace. Returns None if empty after cleanup, or if the
    result carries no digit — a digitless "number" is a title or label
    ("INVOICE", "Invoice Pvelec"), not a document number.
    """
    if s is None:
        return None
    text = s.strip()
    if not text:
        return None
    # Strip internal whitespace.
    text = re.sub(r"\s+", "", text)
    # Strip trailing punctuation (periods, commas, slashes).
    text = text.rstrip(".,:/-")
    if not text:
        return None
    if not any(ch.isdigit() for ch in text):
        return None
    return text


def detect_currency(blocks: tuple) -> str | None:
    """Detect a 3-letter ISO 4217 currency token from text blocks.

    Returns the first known currency code found (source order), or None.
    """
    for block in blocks:
        if "៛" in block.text:
            return "KHR"
        for m in _ISO_CURRENCY.finditer(block.text):
            code = m.group(1)
            if code in _KNOWN_CURRENCIES:
                return code
    return None
