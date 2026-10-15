"""
Deterministic local text-embedding wrapper.

- No LLM. No network. No randomness.
- Loads a sentence-transformers model from a vendored local path.
- Verifies the weights SHA-256 against the pinned value in config.
- Sets HF_HUB_OFFLINE=1 and TRANSFORMERS_OFFLINE=1 BEFORE importing
  sentence_transformers — this must happen before any other import
  so that the library never has a chance to reach the network.

The rest of the codebase interacts with embeddings through this
module and only this module.
"""

# ----------------------------------------------------------------------
# CRITICAL: offline env vars must be set before importing sentence_transformers
# ----------------------------------------------------------------------

import os

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
# setdefault (not []= ) so an explicit override in tests can win.

# ----------------------------------------------------------------------
# Now we can import
# ----------------------------------------------------------------------

import hashlib
from collections.abc import Sequence
from pathlib import Path

import numpy as np

from apmatch.embeddings import config

# ----------------------------------------------------------------------
# Custom exceptions
# ----------------------------------------------------------------------

class EmbeddingModelError(Exception):
    """Raised for any non-recoverable embedding-layer failure."""

class ModelHashMismatch(EmbeddingModelError):
    """Raised when the on-disk weights hash does not match the pinned value."""

# ----------------------------------------------------------------------
# Path resolution
# ----------------------------------------------------------------------

def _repo_root() -> Path:
    # apmatch/embeddings/model.py → repo root is ../../
    return Path(__file__).resolve().parents[2]

def _default_model_dir() -> Path:
    return _repo_root() / "models" / "embeddings" / config.MODEL_DIRNAME

# ----------------------------------------------------------------------
# The model wrapper
# ----------------------------------------------------------------------

class EmbeddingModel:
    """
    Deterministic text encoder.

    Loads once, encodes on demand, caches the model version (SHA-256
    of the weights). Same text always produces the same vector.
    """

    def __init__(self, model_root: Path | str | None = None) -> None:
        self._model_dir = Path(model_root) if model_root else _default_model_dir()

        if not self._model_dir.is_dir():
            raise EmbeddingModelError(
                f"model directory not found: {self._model_dir}\n"
                f"Run EMB-02's vendoring step or point at the correct path."
            )

        weights_path = self._model_dir / "model.safetensors"
        if not weights_path.is_file():
            raise EmbeddingModelError(
                f"model.safetensors not found in {self._model_dir}"
            )

        # Compute the actual hash and compare to the pinned value.
        # This runs once at load; ~1 second on 488 MB.
        actual_hash = self._hash_file(weights_path)
        expected_hash = config.MODEL_WEIGHTS_SHA256
        if expected_hash and not expected_hash.startswith("<") and actual_hash != expected_hash:
            raise ModelHashMismatch(
                f"weights hash mismatch:\n"
                f"  expected: {expected_hash}\n"
                f"  actual:   {actual_hash}\n"
                f"A weight file may have been replaced. Refusing to load."
            )

        self._model_version = actual_hash

        # Import here, not at module top, so env vars are set first.
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(str(self._model_dir), device="cpu")
        # Force eval mode: no dropout, no training-time behavior.
        self._model.eval()

    @staticmethod
    def _hash_file(p: Path) -> str:
        h = hashlib.sha256()
        with p.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()

    @property
    def model_version(self) -> str:
        """SHA-256 of the loaded weights. Logged in every audit row."""
        return self._model_version

    @property
    def dimension(self) -> int:
        """Vector dimension of the model output (384 for MiniLM-L12)."""
        return int(self._model.get_sentence_embedding_dimension())

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        """
        Encode a sequence of strings to vectors.

        Returns a list of lists of floats. Deterministic: identical
        inputs produce identical outputs across processes.
        """
        if not texts:
            return []

        # Truncate per config to keep time and memory bounded.
        truncated = [str(t)[: config.MAX_INPUT_CHARS] for t in texts]

        # normalize_embeddings=True gives us unit-length vectors so
        # cosine similarity reduces to a dot product.
        vecs = self._model.encode(
            truncated,
            batch_size=config.ENCODE_BATCH_SIZE,
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        return vecs.tolist()

    def similarity(self, a: str, b: str) -> float:
        """
        Cosine similarity of two strings, in [-1, 1].

        For typical text pairs, both in [0, 1]. Values below 0.55
        are non-matches per config; values above 0.70 are auto-matches.
        """
        if not a and not b:
            return 1.0  # both empty → identical
        if not a or not b:
            return 0.0
        va, vb = self.encode([a, b])
        return float(np.dot(va, vb))

# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------

if __name__ == "__main__":
    import json
    import sys
    model = EmbeddingModel()
    print(f"model_version: {model.model_version}", file=sys.stderr)
    print(f"dimension:     {model.dimension}", file=sys.stderr)
    result = {
        "version": model.model_version,
        "dimension": model.dimension,
        "pairs": [],
    }
    args = sys.argv[1:]
    # Expect pairs: a1 b1 a2 b2 ...  (at least one pair)
    if len(args) < 2 or len(args) % 2 != 0:
        print("usage: python -m apmatch.embeddings.model <a1> <b1> [<a2> <b2> ...]",
              file=sys.stderr)
        sys.exit(2)
    for i in range(0, len(args), 2):
        a, b = args[i], args[i+1]
        result["pairs"].append({
            "a": a, "b": b,
            "similarity": round(model.similarity(a, b), 4),
        })
    print(json.dumps(result, indent=2))
