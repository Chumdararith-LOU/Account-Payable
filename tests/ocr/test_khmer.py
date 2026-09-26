import os

from apmatch.ocr.engine import OCRResult, TextBlock
from apmatch.ocr.khmer import KhmerOCREngine


def _engine():
    return KhmerOCREngine()


def test_khmer_engine_returns_ocr_result(fixture_image_khmer):
    result = _engine().recognize(fixture_image_khmer)
    assert isinstance(result, OCRResult)
    assert len(result.text_blocks) == 1
    block = result.text_blocks[0]
    assert isinstance(block, TextBlock)
    assert block.text


def test_khmer_output_contains_khmer_unicode(fixture_image_khmer):
    result = _engine().recognize(fixture_image_khmer)
    text = result.text_blocks[0].text
    assert any(0x1780 <= ord(ch) <= 0x17FF for ch in text), f"no Khmer chars in {text!r}"


def test_khmer_deterministic(fixture_image_khmer):
    eng = _engine()
    r1 = eng.recognize(fixture_image_khmer)
    r2 = eng.recognize(fixture_image_khmer)
    assert r1.text_blocks[0].text == r2.text_blocks[0].text
    assert r1.text_blocks[0].bbox == r2.text_blocks[0].bbox


def test_khmer_offline_load():
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    eng = _engine()  # must load from models/khmer with offline env vars set
    assert eng._model is not None
    assert len(eng._tokenizer) == 185
