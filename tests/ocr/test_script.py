from apmatch.ocr._script import count_khmer_codepoints, is_mostly_khmer

KHMER = "កខគ"  # 3 Khmer consonants
KHMER_4 = "កខគឃ"  # 4 Khmer consonants


def test_count_khmer_empty():
    assert count_khmer_codepoints("") == 0


def test_count_khmer_pure():
    assert count_khmer_codepoints(KHMER_4) == len(KHMER_4)


def test_count_khmer_mixed():
    assert count_khmer_codepoints("ab" + KHMER + "cd") == len(KHMER)
    assert count_khmer_codepoints("hello world") == 0


def test_is_mostly_khmer_thresholds():
    # Below min_codepoints (3): reject even with enough total chars.
    assert is_mostly_khmer("ក" + "abcd", 3, 4) is False
    # Exactly min_codepoints and min_total: accept.
    assert is_mostly_khmer(KHMER + "a", 3, 4) is True
    # Enough Khmer chars but below min_total (4): reject.
    assert is_mostly_khmer(KHMER, 3, 4) is False
    # Above both thresholds: accept.
    assert is_mostly_khmer(KHMER_4 + "xy", 3, 4) is True
    # No Khmer at all: reject.
    assert is_mostly_khmer("abcdef", 3, 4) is False
