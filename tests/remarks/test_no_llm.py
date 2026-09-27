"""Structural guard: no LLM / network module may be imported under apmatch/remarks/.

Walks every ``.py`` file under ``apmatch/remarks/``, parses it with ``ast``,
collects the top-level imported module names, and asserts none are on the
blocklist (or contain "llm"). This is what keeps the remark path provably
free of a generative model or any external call.
"""

import ast
from pathlib import Path

REMARKS_DIR = Path(__file__).resolve().parents[2] / "apmatch" / "remarks"

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
    py_files = sorted(REMARKS_DIR.glob("*.py"))
    assert py_files, f"no python files found under {REMARKS_DIR}"
    for path in py_files:
        for name in _imported_names(path):
            assert name not in BLOCKLIST, f"{path.name} imports blocked module {name!r}"
            assert "llm" not in name.lower(), f"{path.name} imports module with 'llm' in name: {name!r}"
