import subprocess, sys
from pathlib import Path

def test_embeddings_offline_verifier_passes():
    repo = Path(__file__).resolve().parents[2]
    r = subprocess.run(
        [sys.executable, str(repo / "scripts" / "verify_offline_embeddings.py")],
        capture_output=True, text=True, timeout=300,
    )
    print(r.stdout)
    print(r.stderr, file=sys.stderr)
    assert r.returncode == 0, (
        f"embeddings offline verifier failed (exit {r.returncode})\n"
        f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    )
    assert "EMBEDDINGS_OFFLINE_OK" in r.stdout
