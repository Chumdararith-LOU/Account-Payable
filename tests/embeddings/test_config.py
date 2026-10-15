"""Tests for apmatch.embeddings.config (EMB-03)."""
import pytest


def test_thresholds_are_decimal():
    from decimal import Decimal

    from apmatch.embeddings.config import SIMILARITY_ACCEPT, SIMILARITY_REVIEW
    assert isinstance(SIMILARITY_ACCEPT, Decimal)
    assert isinstance(SIMILARITY_REVIEW, Decimal)


def test_threshold_ordering():
    from apmatch.embeddings.config import SIMILARITY_ACCEPT, SIMILARITY_REVIEW
    assert SIMILARITY_REVIEW < SIMILARITY_ACCEPT


def test_model_hash_is_sha256_or_placeholder():
    from apmatch.embeddings.config import MODEL_WEIGHTS_SHA256
    h = MODEL_WEIGHTS_SHA256
    if h.startswith("<"):
        pytest.skip("placeholder — pending EMB-02 hash")
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)
