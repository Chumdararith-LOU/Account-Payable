import pytest

from apmatch.ocr.engine import LatinOCREngine, OCRResult, TextBlock
from apmatch.ocr.khmer import KhmerOCREngine
from apmatch.ocr.router import OCRRouter


@pytest.fixture(scope="module")
def router():
    return OCRRouter(latin=LatinOCREngine(), khmer=KhmerOCREngine())


def test_router_returns_ocr_result(router, fixture_image):
    result = router.recognize(fixture_image)
    assert isinstance(result, OCRResult)
    assert len(result.text_blocks) > 0
    assert all(isinstance(b, TextBlock) for b in result.text_blocks)


def test_router_preserves_block_order(router, fixture_image):
    latin = LatinOCREngine().recognize(fixture_image)
    routed = router.recognize(fixture_image)
    assert len(routed.text_blocks) == len(latin.text_blocks)
    assert [b.bbox for b in routed.text_blocks] == [b.bbox for b in latin.text_blocks]


def test_router_stats_are_consistent(router, fixture_image):
    router.recognize(fixture_image)
    s = router.stats()
    assert s["regions"] == s["latin_kept"] + s["khmer_kept"] + s["khmer_rejected"]
    assert s["regions"] > 0


def test_router_deterministic(router, fixture_image):
    r1 = router.recognize(fixture_image)
    r2 = router.recognize(fixture_image)
    assert [b.text for b in r1.text_blocks] == [b.text for b in r2.text_blocks]
    assert [b.bbox for b in r1.text_blocks] == [b.bbox for b in r2.text_blocks]
