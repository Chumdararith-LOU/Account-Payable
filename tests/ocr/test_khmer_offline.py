import subprocess
import sys

from tests.conftest import REPO_ROOT


def test_khmer_offline_verification_passes():
    proc = subprocess.run(  # noqa: S603 — args hardcoded (sys.executable + fixed script path)
        [sys.executable, str(REPO_ROOT / "scripts" / "verify_offline_khmer.py")],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, (
        f"verify_offline_khmer.py failed (rc={proc.returncode}):\n"
        f"stdout: {proc.stdout}\nstderr: {proc.stderr}"
    )
    assert "KHMER_OFFLINE_OK" in proc.stdout
