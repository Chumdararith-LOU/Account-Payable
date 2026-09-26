from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def fixture_image() -> Path:
    return REPO_ROOT / "documents" / "invoice" / "INV_2026_1123.png"


@pytest.fixture(scope="session")
def fixture_image_khmer() -> Path:
    return REPO_ROOT / "tests" / "fixtures" / "khmer_crop.png"
