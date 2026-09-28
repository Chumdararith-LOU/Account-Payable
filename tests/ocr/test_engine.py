import json

from apmatch.ocr.engine import LatinOCREngine, OCRResult, TextBlock, to_prototype_json
from tests.conftest import REPO_ROOT


def _engine():
    return LatinOCREngine()


def test_engine_returns_ocr_result(fixture_image):
    result = _engine().recognize(fixture_image)
    assert isinstance(result, OCRResult)
    assert len(result.text_blocks) > 0
    assert all(isinstance(b, TextBlock) for b in result.text_blocks)
    assert all(b.text for b in result.text_blocks)


def test_bbox_is_rectangle(fixture_image):
    result = _engine().recognize(fixture_image)
    for b in result.text_blocks:
        x0, y0, x1, y1 = b.bbox
        assert x0 < x1, f"bad bbox {b.bbox} for {b.text!r}"
        assert y0 < y1, f"bad bbox {b.bbox} for {b.text!r}"


def test_deterministic(fixture_image):
    eng = _engine()
    r1 = eng.recognize(fixture_image)
    r2 = eng.recognize(fixture_image)
    assert [b.text for b in r1.text_blocks] == [b.text for b in r2.text_blocks]
    assert [b.bbox for b in r1.text_blocks] == [b.bbox for b in r2.text_blocks]


def test_conf_is_float_or_none(fixture_image):
    result = _engine().recognize(fixture_image)
    for b in result.text_blocks:
        assert b.conf is None or (isinstance(b.conf, float) and 0.0 <= b.conf <= 1.0), (
            f"bad conf {b.conf!r} for {b.text!r}"
        )


def test_prototype_json_schema(fixture_image):
    result = _engine().recognize(fixture_image)
    out = to_prototype_json(result)
    assert set(out.keys()) == {"source_file", "text_blocks"}
    assert isinstance(out["source_file"], str)
    assert isinstance(out["text_blocks"], list) and out["text_blocks"]
    for block in out["text_blocks"]:
        assert set(block.keys()) == {"text", "bbox"}
        assert isinstance(block["text"], str)
        assert isinstance(block["bbox"], list)
        assert len(block["bbox"]) == 4
        assert all(isinstance(v, float) for v in block["bbox"])
    # Shape must match an existing prototype file on disk. The prototype
    # files also carry a "tables" key (P1-05); this task is text_blocks only,
    # so our keys must be a subset and the text_blocks shape identical.
    ref = json.loads(
        (REPO_ROOT / "output" / "ocr" / "INV_2026_1123.json").read_text(encoding="utf-8")
    )
    assert set(out.keys()) <= set(ref.keys())
    assert set(ref["text_blocks"][0].keys()) == set(out["text_blocks"][0].keys())
