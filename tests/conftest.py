import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def fixture_image() -> Path:
    return REPO_ROOT / "documents" / "invoice" / "INV_2026_1123.png"


@pytest.fixture(scope="session")
def fixture_image_khmer() -> Path:
    return REPO_ROOT / "tests" / "fixtures" / "khmer_crop.png"


def pytest_report_header(config):
    # Cheap one-line health check. Does not fail; informational.
    try:
        result = subprocess.run(
            ["docker", "compose", "exec", "-T", "postgres",  # noqa: S607 — fixed binary (docker), local dev config
             "pg_isready", "-U", "apmatch"],
            capture_output=True, text=True, timeout=3,
        )
        pg_up = result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pg_up = False
    return [
        f"apmatch: postgres={'up' if pg_up else 'DOWN'}",
        "apmatch: DB-dependent tests will "
        + ("run" if pg_up else "SKIP — start Postgres with "
           "`docker compose up -d postgres`"),
    ]
