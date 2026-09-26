"""Pure script-detection helpers for the Latin/Khmer OCR router.

No I/O, no model imports — only stdlib. Kept in its own module so the
codepoint rules are unit-testable in isolation.
"""

from __future__ import annotations

# Khmer Unicode block + Khmer Symbols block.
_KHMER_RANGES = ((0x1780, 0x17FF), (0x19E0, 0x19FF))


def count_khmer_codepoints(s: str) -> int:
    """Count characters in the Khmer (U+1780–U+17FF) and Khmer Symbols
    (U+19E0–U+19FF) ranges."""
    return sum(1 for ch in s if any(lo <= ord(ch) <= hi for lo, hi in _KHMER_RANGES))


def is_mostly_khmer(s: str, min_codepoints: int, min_total: int) -> bool:
    """True iff s has at least min_codepoints Khmer chars AND at least
    min_total total chars."""
    return len(s) >= min_total and count_khmer_codepoints(s) >= min_codepoints
