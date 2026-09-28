"""Structural guard: no LLM / network module may be imported under apmatch/parse/.

Walks every ``.py`` file under ``apmatch/parse/``, parses it with ``ast``,
collects the imported module names, and asserts none are on the blocklist
(or contain "llm"). A /tmp sanity check proves the walker catches a
synthetic bad import.
"""

import ast
from pathlib import Path

PARSE_DIR = Path(__file__).resolve().parents[2] / "apmatch" / "parse"

BLOCKLIST = {"anthropic", "openai", "requests", "httpx", "urllib", "socket", "transformers"}


def _imported_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    return names


def test_no_llm_or_network_imports():
    py_files = sorted(PARSE_DIR.rglob("*.py"))
    assert py_files, f"no python files found under {PARSE_DIR}"
    for path in py_files:
        for name in _imported_names(path):
            assert name not in BLOCKLIST, f"{path.name} imports blocked module {name!r}"
            assert "llm" not in name.lower(), f"{path.name} imports module with 'llm' in name: {name!r}"


def test_walker_catches_synthetic_bad_import(tmp_path):
    bad = tmp_path / "bad.py"
    bad.write_text("import anthropic\nfrom openai import client\n", encoding="utf-8")
    names = _imported_names(bad)
    assert "anthropic" in names
    assert "openai" in names
