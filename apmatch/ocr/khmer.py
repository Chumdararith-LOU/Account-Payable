"""Deterministic Khmer-script OCR engine wrapper around tror-yong-ocr.

This module wraps the TrorYongOCR model (tror-yong-ocr 0.2.7) for Khmer
(and Latin) text recognition. It is fully deterministic (greedy decoding,
fixed seed), runs CPU-only, makes zero network calls at runtime (offline
env vars are set before tror_yong_ocr is imported, and weights are read
from a local vendored directory), and uses no generative model in the
decision path.

tror-yong-ocr performs RECOGNITION ONLY — it has no text detection.
KhmerOCREngine.recognize() therefore accepts a CROPPED image (a single
text line/region) and returns one TextBlock spanning the whole image with
bbox = (0, 0, width, height). Routing full pages into Khmer/Latin regions
is the script router's job (P1-04b).
"""

from __future__ import annotations

import os
from pathlib import Path

from apmatch.ocr.engine import OCRResult, TextBlock

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL_ROOT = REPO_ROOT / "models" / "khmer"

# Fixed decoding parameters: greedy (temperature=0) is fully deterministic;
# the seed is locked anyway for the sampling path.
MAX_TOKENS = 192
TEMPERATURE = 0.0
SEED = 168


class KhmerOCREngine:
    """Offline TrorYongOCR wrapper for Khmer-script text (cropped regions)."""

    def __init__(self, model_root: Path | str | None = None) -> None:
        root = Path(model_root) if model_root is not None else DEFAULT_MODEL_ROOT
        if not root.is_dir():
            raise FileNotFoundError(
                f"Model root not found: {root}. "
                "Provision it with: cp -RL "
                "~/.cache/huggingface/hub/models--KrorngAI--TrorYongOCR/snapshots/*/. models/khmer/"
            )
        # Offline guards MUST be set before tror_yong_ocr is imported.
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        import tror_yong_ocr as tyo

        self._tyo = tyo
        self._model = tyo.TrorYongOCRModel.from_pretrained(str(root), verbose=False)
        # Determinism: the package passes dropout_p straight into the
        # FUNCTIONAL F.scaled_dot_product_attention, which applies it even
        # in eval mode. Zero every dropout probability so inference is
        # fully deterministic (verified across processes).
        self._model.eval()
        for m in self._model.modules():
            if hasattr(m, "dropout"):
                m.dropout.p = 0.0
        self._tokenizer = tyo.get_tokenizer()
        print(f"KhmerOCREngine: charset size = {len(self._tokenizer)}")

    def recognize(self, image_path: Path | str) -> OCRResult:
        """Recognize Khmer text in a CROPPED single-line image.

        The input must already be a crop of one text line/region
        (tror-yong-ocr does no detection). Returns a single TextBlock
        with bbox = (0, 0, width, height) of the input image.
        """
        from PIL import Image

        img = Image.open(image_path).convert("RGB")
        result = self._tyo.recognize(
            img,
            self._model,
            self._tokenizer,
            max_tokens=MAX_TOKENS,
            temperature=TEMPERATURE,
            seed=SEED,
        )
        bbox = (0.0, 0.0, float(img.width), float(img.height))
        return OCRResult(
            source_file=str(image_path),
            text_blocks=(TextBlock(text=result.text, bbox=bbox),),
        )

    def close(self) -> None:
        # No-op for now; reserved for P1-12.
        pass


def to_prototype_json(result: OCRResult) -> dict:
    """Serialize to the prototype's output/ocr/*.json schema (text_blocks)."""
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

    eng = KhmerOCREngine()
    r = eng.recognize(sys.argv[1])
    print(json.dumps(to_prototype_json(r), ensure_ascii=False, indent=2))
