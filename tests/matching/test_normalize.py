from apmatch.matching.normalize import normalize_currency, normalize_number_text, normalize_text


# --- normalize_text --------------------------------------------------------


def test_normalize_text_collapses_whitespace():
    assert normalize_text("a\tb   c\u00a0d") == "a b c d"


def test_normalize_text_strips_ocr_suffix():
    assert normalize_text("Office Chair/nnw") == "office chair"


def test_normalize_text_keeps_slash_with_uppercase():
    assert normalize_text("P/N 12345") == "p/n 12345"


def test_normalize_text_keeps_slash_with_digits():
    assert normalize_text("1/2 inch") == "1/2 inch"


def test_normalize_text_casefolds():
    assert normalize_text("Office CHAIR") == "office chair"


def test_normalize_text_nfkc():
    assert normalize_text("Ｃhａir") == "chair"


def test_normalize_text_empty():
    assert normalize_text("") == ""


def test_normalize_text_deterministic():
    assert normalize_text("Desk Lamp/uww") == normalize_text("Desk Lamp/uww")


def test_normalize_text_does_not_strip_long_lowercase_suffix():
    # 10 lowercase letters exceeds the 1-8 bound; must NOT be stripped.
    assert normalize_text("/abcdefghij") == "/abcdefghij"


# --- normalize_number_text -------------------------------------------------


def test_normalize_number_removes_whitespace():
    assert normalize_number_text("INV 2026 1123") == "INV20261123"


def test_normalize_number_uppercases():
    assert normalize_number_text("inv-2026-1123") == "INV-2026-1123"


def test_normalize_number_preserves_dashes_and_slashes():
    assert normalize_number_text("PO-2026/0451") == "PO-2026/0451"


def test_normalize_number_empty():
    assert normalize_number_text("") == ""


# --- normalize_currency ----------------------------------------------------


def test_normalize_currency_valid():
    assert normalize_currency("usd") == "USD"


def test_normalize_currency_strips():
    assert normalize_currency("  usd  ") == "USD"


def test_normalize_currency_rejects_short():
    assert normalize_currency("US") == ""


def test_normalize_currency_rejects_long():
    assert normalize_currency("USDD") == ""


def test_normalize_currency_rejects_non_alpha():
    assert normalize_currency("US1") == ""


# --- Determinism -----------------------------------------------------------


def test_normalize_text_deterministic_across_calls():
    s = "Whiteboard/ujwnw  x2"
    assert normalize_text(s) == normalize_text(s)


def test_normalize_number_deterministic_across_calls():
    s = "po 2026 0451"
    assert normalize_number_text(s) == normalize_number_text(s)
