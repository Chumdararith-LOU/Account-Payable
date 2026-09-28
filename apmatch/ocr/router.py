"""Deterministic Latin/Khmer script router for full-page OCR.

This module is deterministic, offline, CPU-only, and uses no LLM. It
takes a full page image, runs LatinOCREngine (PaddleOCR 3.x, which does
detection + recognition) to get text-line regions, and then decides per
region whether the Latin reading or a Khmer re-read (KhmerOCREngine on a
crop of the region) is the better answer.

Cascade strategy (and why): KhmerOCREngine is a seq2seq decoder with NO
confidence signal, so it cannot trigger itself. Instead we use the Latin
engine's per-line confidence as the trigger:
  - conf >= LATIN_HIGH_CONF: the Latin reading is trusted, keep it.
  - conf <  LATIN_LOW_CONF:  the Latin reading is likely a misread of
    Khmer script (PP-OCRv6 emits gibberish with low scores on Khmer),
    so re-read the crop with the Khmer engine and apply the acceptance
    rule.
  - LATIN_LOW_CONF <= conf < LATIN_HIGH_CONF: ambiguous — re-read with
    Khmer and let the acceptance rule pick.
The acceptance rule only accepts a Khmer reading if it actually contains
enough Khmer codepoints; otherwise the Latin text stands. Merging
preserves the Latin engine's block order, so downstream consumers see a
stable layout.
"""

from __future__ import annotations

import io
from pathlib import Path

from apmatch.ocr._script import is_mostly_khmer
from apmatch.ocr.engine import LatinOCREngine, OCRResult, TextBlock, to_prototype_json
from apmatch.ocr.khmer import KhmerOCREngine

# Explicit, named, deterministic thresholds. Change by editing this file.
LATIN_HIGH_CONF = 0.90  # use Latin result without trying Khmer
LATIN_LOW_CONF = 0.55  # definitely try Khmer
KHMER_MIN_CODEPOINTS = 3  # a Khmer response needs >=3 Khmer chars
KHMER_MIN_TOTAL = 4  # and >=4 total chars, else reject


def _pick_winner(latin_text: str, latin_conf: float | None, khmer_text: str) -> str:
    """Accept the Khmer reading only if it is plausibly Khmer; else keep Latin."""
    if is_mostly_khmer(khmer_text, KHMER_MIN_CODEPOINTS, KHMER_MIN_TOTAL):
        return khmer_text
    return latin_text


class OCRRouter:
    """Routes each detected text line to the Latin or Khmer engine."""

    def __init__(
        self,
        latin: LatinOCREngine | None = None,
        khmer: KhmerOCREngine | None = None,
    ) -> None:
        self._latin = latin if latin is not None else LatinOCREngine()
        self._khmer = khmer if khmer is not None else KhmerOCREngine()
        self._stats = {
            "regions": 0,
            "latin_kept": 0,
            "khmer_kept": 0,
            "khmer_rejected": 0,
        }

    def recognize(self, image_path: Path | str) -> OCRResult:
        """Run the full cascade on one page image and merge the result."""
        from PIL import Image

        latin_result = self._latin.recognize(image_path)
        img = Image.open(image_path).convert("RGB")

        merged = []
        for block in latin_result.text_blocks:
            self._stats["regions"] += 1
            conf = block.conf
            if conf is not None and conf >= LATIN_HIGH_CONF:
                merged.append(block)
                self._stats["latin_kept"] += 1
                continue

            x0, y0, x1, y1 = (int(v) for v in block.bbox)
            crop = img.crop((x0, y0, x1, y1))
            buf = io.BytesIO()
            crop.save(buf, format="PNG")
            buf.seek(0)
            khmer_text = self._khmer.recognize(buf).text_blocks[0].text

            winner = _pick_winner(block.text, conf, khmer_text)
            if winner == khmer_text:
                merged.append(TextBlock(text=khmer_text, bbox=block.bbox, conf=None))
                self._stats["khmer_kept"] += 1
            else:
                merged.append(block)
                self._stats["khmer_rejected"] += 1

        return OCRResult(source_file=str(image_path), text_blocks=tuple(merged))

    def stats(self) -> dict:
        return dict(self._stats)

    def close(self) -> None:
        self._latin.close()
        self._khmer.close()


if __name__ == "__main__":
    import contextlib
    import json
    import sys

    # Engine construction prints (HF weight loading, charset log) go to
    # stderr so stdout carries only the JSON document.
    with contextlib.redirect_stdout(sys.stderr):
        router = OCRRouter()
    r = router.recognize(sys.argv[1])
    print(json.dumps(to_prototype_json(r), ensure_ascii=False, indent=2))
    print(f"# stats: {router.stats()}", file=sys.stderr)
