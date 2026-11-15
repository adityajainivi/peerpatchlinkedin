"""Settings in one place. The environment variables exist for tests, not everyday use."""
from __future__ import annotations

import os
from pathlib import Path


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


TOOL_DIR = Path(__file__).resolve().parent.parent
BASE_URL = os.environ.get("PEERPATCH_LINKEDIN_BASE_URL", "https://www.linkedin.com").rstrip("/")
PUBLIC_URL = "https://www.linkedin.com"
HEADLESS = os.environ.get("PEERPATCH_HEADLESS") == "1"

WAIT_MIN_SECONDS = _float_env("PEERPATCH_WAIT_MIN", 2.0)
WAIT_MAX_SECONDS = _float_env("PEERPATCH_WAIT_MAX", 5.0)
LOGIN_TIMEOUT_SECONDS = _float_env("PEERPATCH_LOGIN_TIMEOUT", 300.0)
CHALLENGE_TIMEOUT_SECONDS = _float_env("PEERPATCH_CHALLENGE_TIMEOUT", 300.0)
RATE_LIMIT_PAUSE_SECONDS = _float_env("PEERPATCH_RATE_LIMIT_PAUSE", 60.0)

MAX_SCROLLS = 40
MAX_JOB_PAGES = 40
