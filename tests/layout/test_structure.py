import json

import pytest

from apmatch.layout.structure import LayoutEngine, to_prototype_json
from apmatch.ocr.engine import Table
from tests.conftest import REPO_ROOT


@pytest.fixture(scope="module")
def engine():
    return LayoutEngine()


def test_extract_returns_tables_tuple(engine, fixture_image):
    tables = engine.extract(fixture_image)
    assert isinstance(tables, tuple)
    assert len(tables) >= 1
    assert all(isinstance(t, Table) for t in tables)


def test_table_html_is_nonempty_string(engine, fixture_image):
    tables = engine.extract(fixture_image)
    for t in tables:
        assert isinstance(t.html, str)
        assert len(t.html) > 0
        assert "<table" in t.html


def test_table_bbox_is_rectangle(engine, fixture_image):
    tables = engine.extract(fixture_image)
    for t in tables:
        x0, y0, x1, y1 = t.bbox
        assert x0 < x1
        assert y0 < y1


def test_deterministic(engine, fixture_image):
    t1 = engine.extract(fixture_image)
    t2 = engine.extract(fixture_image)
    assert [t.html for t in t1] == [t.html for t in t2]
    assert [t.bbox for t in t1] == [t.bbox for t in t2]


def test_prototype_json_schema_matches_reference(engine, fixture_image):
    reference = json.loads(
        (REPO_ROOT / "output" / "ocr" / "INV_2026_1123.json").read_text()
    )
    ref_keys = set(reference["tables"][0].keys())
    tables = engine.extract(fixture_image)
    out = to_prototype_json(tables)
    assert set(out.keys()) == {"tables"}
    for entry in out["tables"]:
        assert set(entry.keys()) == ref_keys
