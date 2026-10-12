"""
Regression test for EMB-01h: apmatch/layout/structure.py must not crash
when Paddle returns cell_box_list as a numpy array instead of a Python list.

Paddle 3.3.x (Mac) returns cell_box_list as a numpy ndarray for some inputs
(e.g. documents/invoice/Pasted image.png); Paddle 3.2.x (server) returns a
list. The old `if cells:` raises "ambiguous truth value" on the ndarray case;
the fix checks `cells is not None and len(cells) > 0`.

The synthetic tests exercise the ndarray path directly, so they fail on the
old code regardless of which Paddle is installed (the server's Paddle 3.2.2
returns lists, so the fixture alone would not trigger the bug there). The
fixture tests run the real crash-triggering image through the engines and skip
if the fixture is absent.
"""
from __future__ import annotations

import numpy as np
import pytest

from apmatch.layout.structure import LayoutEngine, _table_from_entry, to_prototype_json
from apmatch.ocr.engine import LatinOCREngine, Table
from tests.conftest import REPO_ROOT

FIXTURE = REPO_ROOT / "documents" / "invoice" / "Pasted image.png"


# --- Synthetic: exercise the numpy ndarray path directly (the real regression) ---


def test_table_from_entry_numpy_cells():
    """A 2-D numpy cell_box_list must compute the bbox, not raise."""
    cells = np.array([[10.0, 20.0, 110.0, 40.0], [10.0, 50.0, 110.0, 70.0]])
    table = _table_from_entry({"pred_html": "<t></t>", "cell_box_list": cells}, page_index=0)
    assert table.bbox == (10.0, 20.0, 110.0, 70.0)


def test_table_from_entry_empty_numpy_cells():
    """An empty numpy array must take the zero-bbox branch, not raise."""
    table = _table_from_entry({"pred_html": "<t></t>", "cell_box_list": np.array([])}, page_index=0)
    assert table.bbox == (0.0, 0.0, 0.0, 0.0)


def test_table_from_entry_none_cells():
    """An explicit None cell_box_list must take the zero-bbox branch, not raise."""
    table = _table_from_entry({"pred_html": "<t></t>", "cell_box_list": None}, page_index=0)
    assert table.bbox == (0.0, 0.0, 0.0, 0.0)


def test_table_from_entry_list_cells_unchanged():
    """A plain Python list (Paddle 3.2.x path) still works — no behavior change."""
    cells = [[10.0, 20.0, 110.0, 40.0], [10.0, 50.0, 110.0, 70.0]]
    table = _table_from_entry({"pred_html": "<t></t>", "cell_box_list": cells}, page_index=0)
    assert table.bbox == (10.0, 20.0, 110.0, 70.0)


# --- Fixture: the real crash-triggering image (skip if absent) ---


@pytest.fixture(scope="module")
def layout_engine():
    return LayoutEngine()


@pytest.fixture(scope="module")
def ocr_engine():
    return LatinOCREngine()


@pytest.mark.skipif(not FIXTURE.exists(), reason="fixture 'documents/invoice/Pasted image.png' not present")
def test_extract_on_pasted_image_returns_tuple(layout_engine):
    """LayoutEngine.extract() on the crash image returns a tuple of Table, no raise."""
    tables = layout_engine.extract(FIXTURE)
    assert isinstance(tables, tuple)
    assert all(isinstance(t, Table) for t in tables)


@pytest.mark.skipif(not FIXTURE.exists(), reason="fixture 'documents/invoice/Pasted image.png' not present")
def test_full_pipeline_on_pasted_image_no_exception(ocr_engine, layout_engine):
    """LatinOCREngine + LayoutEngine + to_prototype_json on the crash image exits cleanly."""
    ocr_engine.recognize(FIXTURE)
    tables = layout_engine.extract(FIXTURE)
    out = to_prototype_json(tables)
    assert isinstance(out, dict)
    assert "tables" in out
