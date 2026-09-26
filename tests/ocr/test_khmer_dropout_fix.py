"""Regression guard for the tror-yong-ocr dropout workaround.

tror-yong-ocr 0.2.7 passes dropout_p into the FUNCTIONAL
F.scaled_dot_product_attention, which applies it even in eval mode.
KhmerOCREngine works around this with model.eval() + zeroed dropout
probabilities. These tests fail if the workaround disappears.
"""

import subprocess
import sys

import torch.nn as nn

from apmatch.ocr.khmer import KhmerOCREngine

_PROBE = (
    "from apmatch.ocr.khmer import KhmerOCREngine; "
    "r = KhmerOCREngine().recognize('tests/fixtures/khmer_crop.png'); "
    "print(r.text_blocks[0].text)"
)


def test_model_is_in_eval_mode():
    eng = KhmerOCREngine()
    assert eng._model.training is False


def test_no_module_has_nonzero_dropout():
    eng = KhmerOCREngine()
    offenders = [
        type(m).__name__
        for m in eng._model.modules()
        if isinstance(m, nn.Dropout) and m.p != 0.0
    ]
    assert not offenders, f"nonzero dropout in: {offenders}"


def test_output_is_stable_across_processes(fixture_image_khmer):
    outs = []
    for _ in range(2):
        proc = subprocess.run(
            [sys.executable, "-c", _PROBE],
            capture_output=True,
            text=True,
            check=True,
        )
        outs.append(proc.stdout)
    assert outs[0] == outs[1], f"cross-process outputs differ: {outs}"
