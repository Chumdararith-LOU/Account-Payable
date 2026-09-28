"""Environment-driven configuration for the APMatch API.

Fail-fast at import time: a missing required var raises ConfigError. No
defaults for secrets. Reads via python-dotenv so local dev works with .env
while production injects real env vars (existing env vars win over .env).

Plain module-level functions/vars instead of pydantic-settings: the config
surface is five vars, and pydantic-settings is not an installed dependency —
adding a package for a settings object buys nothing here.

The offline env vars are set at import time, BEFORE any OCR engine import, so
every process that imports this module inherits the offline guarantee
established in P1-03/04.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

# Offline guarantees (P1-03/04) — must be set before any OCR engine import.
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"

load_dotenv()  # local dev .env; real env vars already set win (override=False)


class ConfigError(RuntimeError):
    """Raised at import time when required configuration is missing or invalid."""


def _required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise ConfigError(f"{name} is required and has no default")
    return value


APMATCH_API_KEY: str = _required("APMATCH_API_KEY")
if len(APMATCH_API_KEY) < 16:
    raise ConfigError("APMATCH_API_KEY must be at least 16 characters")

DATABASE_URL: str = _required("DATABASE_URL")

APMATCH_LOG_LEVEL: str = os.environ.get("APMATCH_LOG_LEVEL", "INFO")
APMATCH_OCR_DEBUG: bool = os.environ.get("APMATCH_OCR_DEBUG", "false").lower() in ("1", "true", "yes")
APMATCH_MAX_UPLOAD_BYTES: int = int(os.environ.get("APMATCH_MAX_UPLOAD_BYTES", str(20 * 1024 * 1024)))
