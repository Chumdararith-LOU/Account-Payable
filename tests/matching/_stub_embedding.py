"""Deterministic stub embedding model for matching-engine tests."""


class StubEmbeddingModel:
    """
    Deterministic stub for engine tests. Returns precomputed
    similarities for known pairs; falls back to 0.0 otherwise.
    """

    model_version = "stub-0000000000000000000000000000000000000000000000000000000000000000"

    def __init__(self, table: dict[tuple[str, str], float]):
        self._table = table

    def similarity(self, a: str, b: str) -> float:
        # case-insensitive lookup, symmetric
        key = (a.lower(), b.lower())
        if key in self._table:
            return self._table[key]
        key = (b.lower(), a.lower())
        return self._table.get(key, 0.0)
