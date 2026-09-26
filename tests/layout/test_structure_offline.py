import subprocess
import sys

from tests.conftest import REPO_ROOT


def test_structure_offline_verification_passes():
    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "verify_offline_structure.py")],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, (
        f"verify_offline_structure.py failed (rc={proc.returncode}):\n"
        f"stdout: {proc.stdout}\nstderr: {proc.stderr}"
    )
    assert "STRUCTURE_OFFLINE_OK" in proc.stdout
