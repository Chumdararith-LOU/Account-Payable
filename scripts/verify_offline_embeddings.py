"""
Prove the embedding model loads and runs with zero network calls.

Monkeypatches socket.socket.connect and socket.create_connection
to raise on any call. Then loads the model from the vendored
path with HF_HUB_OFFLINE=1, encodes a few strings, and prints
a result.

Exits 0 on success (prints EMBEDDINGS_OFFLINE_OK).
Exits 1 on any network call (prints the offending address).
Exits 2 on any other error (prints the traceback).
"""

import os

os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

import socket

_real_connect = socket.socket.connect
_real_create = socket.create_connection


def _blocked_connect(self, addr, *a, **kw):
    raise AssertionError(f"NETWORK CALL: {addr}")


def _blocked_create(addr, *a, **kw):
    raise AssertionError(f"NETWORK CALL: {addr}")


socket.socket.connect = _blocked_connect
socket.create_connection = _blocked_create

try:
    from pathlib import Path

    from sentence_transformers import SentenceTransformer

    model_path = Path(__file__).resolve().parents[1] / "models" / "embeddings" / "paraphrase-multilingual-MiniLM-L12-v2"

    print(f"Loading from {model_path}...")
    model = SentenceTransformer(str(model_path), device="cpu")

    vecs = model.encode([
        "Office Chair",
        "Chair, office, metal frame, black",
        "Desk Lamp",
    ])

    # Print a couple of sanity numbers
    print(f"embeddings shape: {vecs.shape}")
    from numpy import dot
    from numpy.linalg import norm
    def cos(a, b):
        return float(dot(a, b) / (norm(a) * norm(b)))
    sim_office_chair = cos(vecs[0], vecs[1])
    sim_chair_desk = cos(vecs[0], vecs[2])
    print(f"Office Chair <-> Chair, office, metal frame: {sim_office_chair:.4f}")
    print(f"Office Chair <-> Desk Lamp:                  {sim_chair_desk:.4f}")

    if not (sim_office_chair > sim_chair_desk):
        print("WARNING: semantic similarity did not behave as expected")
    print("EMBEDDINGS_OFFLINE_OK")
    raise SystemExit(0)
except AssertionError as e:
    print(str(e), flush=True)
    raise SystemExit(1) from e
except SystemExit:
    raise
except Exception:
    import traceback
    traceback.print_exc()
    raise SystemExit(2) from None
finally:
    socket.socket.connect = _real_connect
    socket.create_connection = _real_create
