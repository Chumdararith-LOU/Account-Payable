"""Prove apmatch.ocr.khmer makes zero network calls at runtime.

Monkeypatches socket.socket.connect and socket.create_connection to raise
AssertionError BEFORE tror_yong_ocr is imported, then runs a full Khmer
OCR pass on the crop fixture. Prints KHMER_OFFLINE_OK and exits 0 if no
network call was made; prints the offending address and exits 1 otherwise.
"""

import socket
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "khmer_crop.png"
sys.path.insert(0, str(REPO_ROOT))


def _blocked_connect(self, address, *args, **kwargs):
    raise AssertionError(f"NETWORK CALL: {address}")


def _blocked_create_connection(address, *args, **kwargs):
    raise AssertionError(f"NETWORK CALL: {address}")


# Install the blocks BEFORE any tror_yong_ocr import happens.
socket.socket.connect = _blocked_connect
socket.create_connection = _blocked_create_connection

from apmatch.ocr.khmer import KhmerOCREngine  # noqa: E402


def main() -> int:
    try:
        eng = KhmerOCREngine()
        result = eng.recognize(FIXTURE)
    except AssertionError as e:
        print(f"OFFLINE_VIOLATION: {e}")
        return 1
    print(f"KHMER_OFFLINE_OK ({result.text_blocks[0].text!r}, no network calls)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
