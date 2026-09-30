"""Full-stack docker smoke test (opt-in, amd64-only).

This is the install-and-run proof: it runs scripts/smoke_test.sh, which brings
up the compose stack, POSTs the four fixture images, verifies the audit trail,
and tears down.

It runs on real linux/amd64 hardware, NOT under QEMU emulation: Paddle's
oneDNN CPU backend fails under QEMU (see D-062). Local Apple Silicon dev
machines skip it even with APMATCH_RUN_SMOKE=1; the correct home is CI on an
amd64 runner (see .github/workflows/ci.yml).
"""

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _is_amd64_linux() -> bool:
    return (
        sys.platform.startswith("linux")
        and platform.machine() in ("x86_64", "amd64")
    )


pytestmark = [
    pytest.mark.smoke,
    pytest.mark.skipif(
        shutil.which("docker") is None,
        reason="docker not on PATH",
    ),
    pytest.mark.skipif(
        os.environ.get("APMATCH_RUN_SMOKE") != "1",
        reason="set APMATCH_RUN_SMOKE=1 to run the full-stack smoke test",
    ),
    pytest.mark.skipif(
        not _is_amd64_linux(),
        reason=(
            "smoke test requires linux/amd64 (Paddle oneDNN backend "
            "fails under QEMU emulation; see D-062)"
        ),
    ),
]


def test_smoke_script_exits_zero():
    # Generate a key so the script doesn't prompt.
    env = os.environ.copy()
    if "APMATCH_API_KEY" not in env:
        import secrets

        env["APMATCH_API_KEY"] = secrets.token_hex(32)
    result = subprocess.run(  # noqa: S603  # fixed repo script path, not untrusted input
        [str(REPO_ROOT / "scripts" / "smoke_test.sh")],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
    )
    print(result.stdout)
    print(result.stderr)
    assert result.returncode == 0, (
        f"smoke test failed with code {result.returncode}\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "SMOKE OK" in result.stdout
