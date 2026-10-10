"""Prove apmatch.ocr.engine makes zero network calls at runtime.

Monkeypatches socket.socket.connect and socket.create_connection to raise
AssertionError BEFORE paddleocr is imported, then runs a full OCR pass on
the fixture. Prints OFFLINE_OK and exits 0 if no network call was made;
prints the offending address and exits 1 otherwise.
"""

import socket
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
# In the container the fixture ships next to this script (COPY scripts/);
# on a dev checkout it lives under documents/.
FIXTURE = (
    Path(__file__).resolve().parent / "INV_2026_1123.png"
    if (Path(__file__).resolve().parent / "INV_2026_1123.png").exists()
    else REPO_ROOT / "documents" / "invoice" / "INV_2026_1123.png"
)
sys.path.insert(0, str(REPO_ROOT))


def _blocked_connect(self, address, *args, **kwargs):
    raise AssertionError(f"NETWORK CALL: {address}")


def _blocked_create_connection(address, *args, **kwargs):
    raise AssertionError(f"NETWORK CALL: {address}")


# Install the blocks BEFORE any paddle/paddleocr import happens.
socket.socket.connect = _blocked_connect
socket.create_connection = _blocked_create_connection

from apmatch.ocr.engine import LatinOCREngine  # noqa: E402


def main() -> int:
    try:
        eng = LatinOCREngine()
        result = eng.recognize(FIXTURE)
    except AssertionError as e:
        print(f"OFFLINE_VIOLATION: {e}")
        return 1
    print(f"OFFLINE_OK ({len(result.text_blocks)} text blocks, no network calls)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
