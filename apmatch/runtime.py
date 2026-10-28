"""
Runtime environment detection. Answers "which device should
heavy libraries (Paddle, torch) use?"

Controlled by the APMATCH_DEVICE environment variable.
Valid values: "cpu" (default), "cuda".

Why a single module: the four engine classes (OCR, Khmer,
Layout, Embeddings) must all make the SAME device decision.
Centralizing prevents drift.
"""

import os

VALID_DEVICES = ("cpu", "cuda")


def get_device() -> str:
    """Return the device string ('cpu' or 'cuda')."""
    device = os.environ.get("APMATCH_DEVICE", "cpu").lower().strip()
    if device not in VALID_DEVICES:
        raise ValueError(
            f"APMATCH_DEVICE={device!r} is invalid. "
            f"Must be one of {VALID_DEVICES}."
        )
    return device
