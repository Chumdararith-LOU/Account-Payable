"""Structural guard: no LLM / network module may be imported under apmatch/scoring/.

The routing decision is the system's final exit; proving it contains no
generative or network path is a precondition for the bank pitch. Walks every
``.py`` under ``apmatch/scoring/``, parses it with ``ast``, and asserts none of
the imported top-level modules are on the blocklist (or contain "llm").
"""

import ast
from pathlib import Path

SCORING_DIR = Path(__file__).resolve().parents[2] / "apmatch" / "scoring"

BLOCKLIST = {"anthropic", "openai", "requests", "httpx", "urllib", "socket", "transformers"}


def _imported_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module.split(".")[0])
    return names


def test_no_llm_or_network_imports():
    py_files = sorted(SCORING_DIR.rglob("*.py"))
    assert py_files, f"no python files found under {SCORING_DIR}"
    for path in py_files:
        for name in _imported_names(path):
            assert name not in BLOCKLIST, f"{path.name} imports blocked module {name!r}"
            assert "llm" not in name.lower(), f"{path.name} imports module with 'llm' in name: {name!r}"


def test_guard_catches_a_bad_import(tmp_path):
    # Sanity-check the walker: a deliberately-broken module must be flagged.
    bad = tmp_path / "bad.py"
    bad.write_text("import requests\n", encoding="utf-8")
    names = _imported_names(bad)
    assert "requests" in names
    assert any(n in BLOCKLIST for n in names)
