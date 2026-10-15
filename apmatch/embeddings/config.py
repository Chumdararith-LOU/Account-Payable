"""
Embedding-layer constants. Not config files.

Changing any of these values is a task, not a config edit — every
threshold is a decision that affects matching outcomes and must be
accompanied by a decision record (see docs/DECISIONS.md).
"""

from decimal import Decimal

# ----------------------------------------------------------------------
# Model identity
# ----------------------------------------------------------------------

# Directory name under models/embeddings/
MODEL_DIRNAME = "paraphrase-multilingual-MiniLM-L12-v2"

# Expected SHA-256 of model.safetensors. If the file on disk has a
# different hash, EmbeddingModel raises at load time — a silent
# weight swap would corrupt the audit trail (D-080).
MODEL_WEIGHTS_SHA256 = "eaa086f0ffee582aeb45b36e34cdd1fe2d6de2bef61f8a559a1bbc9bd955917b"

# ----------------------------------------------------------------------
# Similarity thresholds
# ----------------------------------------------------------------------

# Cosine similarity bands. Determined empirically from
# EMB-02's reference numbers (paraphrase 0.74, unrelated 0.45).
# The bands are deliberately wide in the middle: any score in
# the "review" band is a match, but the pipeline routes the
# decision to a human reviewer. This is how we handle the
# model's moderate discrimination power.

# Scores >= this are accepted as matches without review.
SIMILARITY_ACCEPT = Decimal("0.70")

# Scores in [SIMILARITY_REVIEW, SIMILARITY_ACCEPT) are matches
# that require human review before auto-approval.
SIMILARITY_REVIEW = Decimal("0.55")

# Scores < SIMILARITY_REVIEW are not matches.
# (SIMILARITY_REJECT is a documentation alias; not used in code.)

# ----------------------------------------------------------------------
# Runtime
# ----------------------------------------------------------------------

# Batch size for encode(). Larger = faster but more memory.
# 32 keeps peak memory under ~100 MB on the server.
ENCODE_BATCH_SIZE = 32

# Truncate any input longer than this many characters before
# encoding. Line-item descriptions are never longer than ~300 chars
# in practice. Truncation keeps encode time bounded.
MAX_INPUT_CHARS = 512

__all__ = [
    "ENCODE_BATCH_SIZE",
    "MAX_INPUT_CHARS",
    "MODEL_DIRNAME",
    "MODEL_WEIGHTS_SHA256",
    "SIMILARITY_ACCEPT",
    "SIMILARITY_REVIEW",
]
