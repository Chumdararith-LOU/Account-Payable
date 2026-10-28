"""Deterministic table extraction via PP-StructureV3.

This module wraps PaddleOCR 3.7.0's PP-StructureV3 pipeline for table
detection and structure recognition. It is fully deterministic, runs
CPU-only, makes zero network calls at runtime (offline env vars are set
before paddleocr is imported, and model weights are read from a local
vendored directory), and uses no generative model anywhere.

Table extraction lives in its own engine, called independently of the
Latin/Khmer OCR router. Whether the router should also run the table
pipeline is a later decision (P1-08+).
"""

from __future__ import annotations

import os
from pathlib import Path

from apmatch.ocr.engine import Table

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL_ROOT = REPO_ROOT / "models" / "paddleocr"

# Model subdirectory names inside the vendored cache root, keyed by the
# PPStructureV3 constructor kwarg that points at them. Discovered in P1-05
# Sub B from the PP-StructureV3 pipeline config.
_MODEL_DIRS = {
    "layout_detection_model_dir": "PP-DocLayout_plus-L",
    "region_detection_model_dir": "PP-DocBlockLayout",
    "doc_orientation_classify_model_dir": "PP-LCNet_x1_0_doc_ori",
    "table_orientation_classify_model_dir": "PP-LCNet_x1_0_doc_ori",
    "doc_unwarping_model_dir": "UVDoc",
    "text_detection_model_dir": "PP-OCRv5_server_det",
    "textline_orientation_model_dir": "PP-LCNet_x1_0_textline_ori",
    "text_recognition_model_dir": "PP-OCRv5_server_rec",
    "table_classification_model_dir": "PP-LCNet_x1_0_table_cls",
    "wired_table_structure_recognition_model_dir": "SLANeXt_wired",
    "wireless_table_structure_recognition_model_dir": "SLANet_plus",
    "wired_table_cells_detection_model_dir": "RT-DETR-L_wired_table_cell_det",
    "wireless_table_cells_detection_model_dir": "RT-DETR-L_wireless_table_cell_det",
}


class LayoutEngine:
    """Offline PP-StructureV3 wrapper for table extraction."""

    def __init__(self, model_root: Path | str | None = None) -> None:
        root = Path(model_root) if model_root is not None else DEFAULT_MODEL_ROOT
        if not root.is_dir():
            raise FileNotFoundError(
                f"Model root not found: {root}. "
                "Provision it with: cp -R ~/.paddlex/official_models/. models/paddleocr/"
            )
        # Offline guards MUST be set before paddleocr is imported.
        os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        from paddleocr import PPStructureV3

        from apmatch.runtime import get_device

        kwargs = {kwarg: str(root / subdir) for kwarg, subdir in _MODEL_DIRS.items()}
        # AP invoices contain no formulas, machine-readable seals, or charts.
        # Disabling these sub-pipelines skips their model construction (and
        # the 702 MB PP-FormulaNet_plus-L weights) entirely.
        # Paddlex device vocabulary is "cpu"/"gpu", not torch's "cuda".
        paddle_device = "gpu" if get_device() == "cuda" else "cpu"
        self._pipeline = PPStructureV3(
            use_formula_recognition=False,
            use_seal_recognition=False,
            use_chart_recognition=False,
            device=paddle_device,
            **kwargs,
        )

    def extract(self, image_path: Path | str) -> tuple[Table, ...]:
        """Run table extraction on one image, returning tables in source order."""
        result = self._pipeline.predict(str(image_path))
        r0 = result[0]
        tables = []
        for entry in r0.get("table_res_list", []):
            tables.append(_table_from_entry(entry, page_index=r0.get("page_index") or 0))
        return tuple(tables)

    def close(self) -> None:
        # No-op for now; reserved for P1-12.
        pass


def _table_from_entry(entry: dict, page_index: int) -> Table:
    """Convert one PP-StructureV3 table_res_list entry into a Table."""
    html = entry.get("pred_html", "")
    cells = entry.get("cell_box_list", [])
    # `cells` may arrive as a Python list (Paddle 3.2.2) or as a
    # numpy ndarray (Paddle 3.3.1, some inputs). `if cells:`
    # raises on the ndarray case (ambiguous truth value). Check
    # explicitly for None and length.
    if cells is not None and len(cells) > 0:
        xs0 = [float(c[0]) for c in cells]
        ys0 = [float(c[1]) for c in cells]
        xs1 = [float(c[2]) for c in cells]
        ys1 = [float(c[3]) for c in cells]
        bbox = (min(xs0), min(ys0), max(xs1), max(ys1))
    else:
        bbox = (0.0, 0.0, 0.0, 0.0)
    return Table(html=html, bbox=bbox, page_index=page_index)


def to_prototype_json(tables: tuple[Table, ...]) -> dict:
    """Serialize tables to the prototype's output/ocr/*.json schema exactly.

    The prototype files carry `tables` as a list of dicts with a single
    "html" key. No extra keys are added here.
    """
    return {"tables": [{"html": t.html} for t in tables]}


if __name__ == "__main__":
    import contextlib
    import json
    import sys

    # Engine construction prints (model creation, weight loading) go to
    # stderr so stdout carries only the JSON document.
    with contextlib.redirect_stdout(sys.stderr):
        engine = LayoutEngine()
    tables = engine.extract(sys.argv[1])
    print(json.dumps(to_prototype_json(tables), ensure_ascii=False, indent=2))
    print(f"# stats: {dict(tables=len(tables))}", file=sys.stderr)
