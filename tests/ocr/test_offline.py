import subprocess
import sys

from tests.conftest import REPO_ROOT


def test_offline_verification_passes():
    proc = subprocess.run(  # noqa: S603 — args hardcoded (sys.executable + fixed script path)
        [sys.executable, str(REPO_ROOT / "scripts" / "verify_offline.py")],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, (
        f"verify_offline.py failed (rc={proc.returncode}):\n"
        f"stdout: {proc.stdout}\nstderr: {proc.stderr}"
    )
    assert "OFFLINE_OK" in proc.stdout
