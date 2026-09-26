"""Deterministic Latin/numeric OCR engine wrapper around PaddleOCR 3.x.

This module wraps PaddleOCR 3.7.0 (PP-OCRv6_medium det/rec) for
Latin-script and numeric text recognition. It is fully deterministic,
runs CPU-only, makes zero network calls at runtime (offline env vars are
set before paddleocr is imported, and model weights are read from a
local vendored directory), and uses no generative model anywhere.
Khmer script is out of scope here (P1-04); table/layout extraction is
P1-05.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL_ROOT = REPO_ROOT / "models" / "paddleocr"

# Model subdirectory names inside the vendored cache root, keyed by the
# PaddleOCR 3.x constructor kwarg that points at them.
_MODEL_DIRS = {
    "doc_orientation_classify_model_dir": "PP-LCNet_x1_0_doc_ori",
    "doc_unwarping_model_dir": "UVDoc",
    "text_detection_model_dir": "PP-OCRv6_medium_det",
    "text_recognition_model_dir": "PP-OCRv6_medium_rec",
}


@dataclass(frozen=True)
class TextBlock:
    """One recognized text line. bbox = (x0, y0, x1, y1) with x0<x1, y0<y1.

    conf is the engine's per-line recognition confidence in [0, 1] when
    the engine provides one (PaddleOCR rec_scores), else None.
    """

    text: str
    bbox: tuple[float, float, float, float]
    conf: float | None = field(default=None)


@dataclass(frozen=True)
class OCRResult:
    """All text lines recognized in one image, in engine output order."""

    source_file: str
    text_blocks: tuple[TextBlock, ...]


class LatinOCREngine:
    """Offline PaddleOCR 3.x wrapper for Latin/numeric text."""

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
        from paddleocr import PaddleOCR

        kwargs = {kwarg: str(root / subdir) for kwarg, subdir in _MODEL_DIRS.items()}
        self._ocr = PaddleOCR(use_textline_orientation=False, lang="en", **kwargs)

    def recognize(self, image_path: Path | str) -> OCRResult:
        """Run OCR on one image and return text blocks in engine order."""
        result = self._ocr.predict(str(image_path))
        r0 = result[0]
        scores = r0.get("rec_scores")
        blocks = []
        for i, (text, poly) in enumerate(zip(r0["rec_texts"], r0["rec_polys"])):
            xs = [pt[0] for pt in poly]
            ys = [pt[1] for pt in poly]
            bbox = (float(min(xs)), float(min(ys)), float(max(xs)), float(max(ys)))
            conf = float(scores[i]) if scores is not None and i < len(scores) else None
            blocks.append(TextBlock(text=text, bbox=bbox, conf=conf))
        return OCRResult(source_file=str(image_path), text_blocks=tuple(blocks))

    def close(self) -> None:
        # No-op for now; reserved for P1-12.
        pass


def to_prototype_json(result: OCRResult) -> dict:
    """Serialize to the prototype's output/ocr/*.json schema exactly."""
    return {
        "source_file": result.source_file,
        "text_blocks": [
            {"text": b.text, "bbox": [b.bbox[0], b.bbox[1], b.bbox[2], b.bbox[3]]}
            for b in result.text_blocks
        ],
    }


if __name__ == "__main__":
    import sys
    import json

    eng = LatinOCREngine()
    r = eng.recognize(sys.argv[1])
    print(json.dumps(to_prototype_json(r), ensure_ascii=False, indent=2))
