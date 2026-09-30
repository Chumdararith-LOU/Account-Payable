"""Full-stack docker smoke test (opt-in).

Runs scripts/smoke_test.sh, which brings up the compose stack, POSTs the four
fixture images, verifies the audit trail, and tears down. Skipped by default;
set APMATCH_RUN_SMOKE=1 to run it. Takes minutes and requires Docker.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

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
