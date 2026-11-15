# PeerPatch LinkedIn Scraper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A double-click tool that drives the person's own Google Chrome to collect LinkedIn hiring posts from the last 48 hours and job listings from the last 7 days for a job title, and saves them as two CSVs and an HTML report.

**Architecture:** A small Python package. `browser.py` owns Chrome (launch, login, walls, waits, running in-page scripts). `extract.js` reads posts and job cards from the DOM. `posts.py` and `jobs.py` build URLs, page through results and turn raw dicts into dataclasses. `filters.py` and `timeparse.py` are pure helpers. `report.py` writes files and knows nothing about browsers. `cli.py` wires it together.

**Tech Stack:** Python 3.9+, Playwright for Python (sync API, `channel="chrome"`), pytest. No other runtime dependencies.

**Spec:** `docs/superpowers/specs/2026-11-15-linkedin-scraper-design.md`

## Global Constraints

- Python 3.9 or newer. Every module starts with `from __future__ import annotations`. No `match`, no runtime `X | Y` types.
- Runtime dependency: `playwright` only. Test dependency: `pytest`.
- Chrome is launched with `launch_persistent_context(<profile>, channel="chrome")`. Profile folder default: `chrome-profile/` next to the tool. Visible window unless `PEERPATCH_HEADLESS=1`.
- The tool never asks for, reads or stores a password.
- Defaults: location `India`, `--max-posts 100`, `--max-jobs 200`, `--post-hours 48` (1 to 168), `--job-days 7`.
- Random wait between actions: 2 to 5 seconds. At most 40 scrolls and 40 job pages per run.
- Posts search URL: `/search/results/content/?keywords="<job>" hiring&datePosted="past-week"&sortBy="date_posted"`.
- Jobs URL: `/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords=..&location=..&f_TPR=r<days*86400>&sortBy=DD&start=<n>`.
- Links written into results always use `https://www.linkedin.com`, even when tests point `PEERPATCH_LINKEDIN_BASE_URL` somewhere else.
- CSVs: UTF-8 with BOM. Results folder: `results/<job>_<location>_<YYYY-MM-DD_HHMM>/` holding `posts.csv`, `jobs.csv`, `report.html` and, with `--debug`, `debug/`.
- Console messages are plain ASCII (no curly quotes, no ellipsis character).
- Read config through the module (`config.BASE_URL`), never `from .config import BASE_URL`, so tests can monkeypatch it.

## Review Focus

1. A Windows console that can't print `₹` or `→` (cp1252) should print `?` instead of crashing. Pinned in Task 8.
2. A post whose text starts with `=`, `+`, `@` or `-2+3` should not run as a formula when the CSV is opened in Excel. Pinned in Task 7.
3. Job titles with quotes, `C++`, `R&D` or Hindi script should produce valid URLs and a usable folder name. Pinned in Tasks 5, 6 and 7.
4. Running twice in the same minute, or with the first Chrome window still open, should give a new folder and a clear "already open" message. Pinned in Tasks 3 and 7.
5. LinkedIn answering the jobs listing with HTTP 999 should stop the jobs half with a message, not crash. Pinned in Task 6.

---

## File map

```
peerpatchlinkedin/
  .gitignore  .gitattributes  requirements.txt  requirements-dev.txt  pytest.ini
  run.command  run.bat  README.md
  peerpatch_linkedin/
    __init__.py  __main__.py  config.py  timeparse.py  filters.py
    browser.py  extract.js  posts.py  jobs.py  report.py  cli.py
  tests/
    __init__.py  conftest.py  linkedin_markup.py  fake_linkedin.py
    test_timeparse.py  test_filters.py  test_browser.py  test_extract.py
    test_posts.py  test_jobs.py  test_report.py  test_cli.py  test_e2e.py
```

All commands run from the repo root inside a virtualenv:

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt -r requirements-dev.txt
```

---

### Task 1: Project skeleton, config and timestamps

**Files:**
- Create: `.gitignore`, `.gitattributes`, `requirements.txt`, `requirements-dev.txt`, `pytest.ini`
- Create: `peerpatch_linkedin/__init__.py`, `peerpatch_linkedin/config.py`, `peerpatch_linkedin/timeparse.py`
- Create: `tests/__init__.py`, `tests/linkedin_markup.py` (only `urn_for` for now), `tests/test_timeparse.py`

**Interfaces:**
- Produces: `config.TOOL_DIR: Path`, `config.BASE_URL: str`, `config.PUBLIC_URL: str`, `config.HEADLESS: bool`, `config.WAIT_MIN_SECONDS`, `config.WAIT_MAX_SECONDS`, `config.LOGIN_TIMEOUT_SECONDS`, `config.CHALLENGE_TIMEOUT_SECONDS`, `config.RATE_LIMIT_PAUSE_SECONDS: float`, `config.MAX_SCROLLS`, `config.MAX_JOB_PAGES: int`
- Produces: `timeparse.urn_to_datetime(urn: str) -> datetime | None` (aware UTC), `timeparse.relative_label_to_hours(label: str) -> float | None`
- Produces (tests): `tests.linkedin_markup.urn_for(when: datetime, kind: str = "activity", salt: int = 12345) -> str`

- [ ] **Step 1: Write the setup files**

`.gitignore`:
```
.venv/
__pycache__/
*.pyc
.pytest_cache/
chrome-profile/
results/
```

`.gitattributes`:
```
*.bat     text eol=crlf
*.command text eol=lf
*.sh      text eol=lf
```

`requirements.txt`:
```
playwright>=1.45,<2
```

`requirements-dev.txt`:
```
pytest>=7
```

`pytest.ini`:
```ini
[pytest]
testpaths = tests
pythonpath = .
```

`peerpatch_linkedin/__init__.py`:
```python
"""Collect LinkedIn hiring posts and job listings for a job title."""
```

`tests/__init__.py`: empty file.

- [ ] **Step 2: Write `config.py`**

```python
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
```

- [ ] **Step 3: Write the failing tests**

`tests/linkedin_markup.py` (start of file; later tasks add to it):
```python
"""HTML shaped like LinkedIn's pages, with the content swapped for test data."""
from __future__ import annotations

import html
from datetime import datetime


def urn_for(when: datetime, kind: str = "activity", salt: int = 12345) -> str:
    """Build a post URN whose top 41 bits hold `when`, the way LinkedIn's do."""
    ms = round(when.timestamp() * 1000)
    return f"urn:li:{kind}:{(ms << 22) | (salt & 0x3FFFFF)}"
```

`tests/test_timeparse.py`:
```python
from datetime import datetime, timezone

import pytest

from peerpatch_linkedin.timeparse import relative_label_to_hours, urn_to_datetime
from tests.linkedin_markup import urn_for

WHEN = datetime(2026, 11, 14, 9, 30, 15, 123000, tzinfo=timezone.utc)


@pytest.mark.parametrize("kind", ["activity", "ugcPost", "share"])
def test_post_id_decodes_to_exact_creation_time(kind):
    assert urn_to_datetime(urn_for(WHEN, kind)) == WHEN


def test_urn_inside_a_link_still_decodes():
    link = f"https://www.linkedin.com/feed/update/{urn_for(WHEN)}/?utm_source=share"
    assert urn_to_datetime(link) == WHEN


@pytest.mark.parametrize("bad", ["", "urn:li:activity:12345", "urn:li:comment:7392847561234567890", "nonsense"])
def test_ids_without_a_usable_time_give_none(bad):
    assert urn_to_datetime(bad) is None


@pytest.mark.parametrize("label, hours", [
    ("now", 0.0), ("Just now", 0.0), ("45s", 45 / 3600), ("5m", 5 / 60), ("3h", 3.0),
    ("1d • Edited •", 24.0), ("2w", 336.0), ("3mo", 2160.0), ("1yr", 8760.0),
    ("23 hours ago", 23.0), ("1 day ago • Edited", 24.0), ("2 weeks ago", 336.0),
])
def test_relative_labels(label, hours):
    assert relative_label_to_hours(label) == pytest.approx(hours)


@pytest.mark.parametrize("label", ["", "Promoted", "Edited"])
def test_unreadable_labels_give_none(label):
    assert relative_label_to_hours(label) is None
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_timeparse.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'peerpatch_linkedin.timeparse'`

- [ ] **Step 5: Write `timeparse.py`**

```python
"""Turn LinkedIn post IDs and "2d"-style labels into times."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

_URN_ID = re.compile(r"urn:li:(?:activity|share|ugcPost):(\d{15,20})")
_EARLIEST_MS = 1_262_304_000_000  # 2010-01-01
_LATEST_MS = 4_102_444_800_000  # 2100-01-01

_SHORT = re.compile(r"^\s*(\d+)\s*(mo|yr|s|m|h|d|w|y)\b", re.IGNORECASE)
_LONG = re.compile(r"(\d+)\s*(second|minute|hour|day|week|month|year)s?\s+ago", re.IGNORECASE)
_HOURS = {
    "s": 1 / 3600, "second": 1 / 3600,
    "m": 1 / 60, "minute": 1 / 60,
    "h": 1.0, "hour": 1.0,
    "d": 24.0, "day": 24.0,
    "w": 168.0, "week": 168.0,
    "mo": 720.0, "month": 720.0,
    "y": 8760.0, "yr": 8760.0, "year": 8760.0,
}


def urn_to_datetime(urn: str) -> datetime | None:
    """LinkedIn post IDs keep the creation time (ms since 1970) in their top 41 bits."""
    match = _URN_ID.search(urn or "")
    if not match:
        return None
    ms = int(match.group(1)) >> 22
    if not _EARLIEST_MS <= ms <= _LATEST_MS:
        return None
    return datetime.fromtimestamp(ms // 1000, tz=timezone.utc) + timedelta(milliseconds=ms % 1000)


def relative_label_to_hours(label: str) -> float | None:
    """'5h', '1d • Edited', '2 weeks ago', 'now' -> hours. None if it can't tell."""
    text = (label or "").strip().lower()
    if not text:
        return None
    if text.startswith("now") or "just now" in text:
        return 0.0
    match = _LONG.search(text) or _SHORT.match(text)
    if not match:
        return None
    return int(match.group(1)) * _HOURS[match.group(2).lower()]
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_timeparse.py -q`
Expected: all pass

- [ ] **Step 7: Commit**

```bash
git add .gitignore .gitattributes requirements*.txt pytest.ini peerpatch_linkedin tests
git commit -m "Add project skeleton, config and post-time decoding"
```

---

### Task 2: Hiring and job-seeker filters

**Files:**
- Create: `peerpatch_linkedin/filters.py`
- Test: `tests/test_filters.py`

**Interfaces:**
- Produces: `filters.is_hiring_post(text: str) -> bool`, `filters.mentions_title(text: str, job_title: str) -> bool`

- [ ] **Step 1: Write the failing tests**

`tests/test_filters.py`:
```python
import pytest

from peerpatch_linkedin.filters import is_hiring_post, mentions_title


@pytest.mark.parametrize("text", [
    "We're hiring a Data Analyst in Bengaluru!",
    "We’re Hiring! Data Analyst, 2+ yrs",  # curly apostrophe
    "#NowHiring data analysts for our Pune office",
    "Job openings for analysts. Apply now.",
    "Openings for freshers in Gurugram",
    "We have 3 vacancies in the analytics team",
    "Looking for a Data Analyst to join my team. DM me.",
    "Please share your updated CV at jobs@acme.in",
    "Referrals welcome for this role",
    "Walk-in drive this Saturday, immediate joiners preferred",
    "Open positions in our data team",
])
def test_hiring_posts_are_kept(text):
    assert is_hiring_post(text)


@pytest.mark.parametrize("text", [
    "I'm looking for a new role as a Data Analyst. #OpenToWork",
    "I am actively seeking full-time opportunities. Hiring managers, DM me!",
    "Open to work: data analyst, 2 years SQL. Referrals appreciated.",
    "Im looking for a job in analytics, any referrals?",
    "I am an immediate joiner, please share openings",
])
def test_job_seeker_posts_are_dropped(text):
    assert not is_hiring_post(text)


@pytest.mark.parametrize("text", [
    "Five SQL tricks every data analyst should know",
    "What an eye-opening conference",
    "",
])
def test_posts_without_hiring_language_are_dropped(text):
    assert not is_hiring_post(text)


@pytest.mark.parametrize("text, title, expected", [
    ("Hiring Data Analysts in Pune", "data analyst", True),
    ("Hiring analysts in Pune", "data analyst", False),
    ("We need a C++ developer", "C++ developer", True),
    ("She said the engineer left", "AI engineer", False),
    ("Hiring an AI engineer", "AI engineer", True),
    ("anything", "", False),
])
def test_mentions_title(text, title, expected):
    assert mentions_title(text, title) is expected
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_filters.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'peerpatch_linkedin.filters'`

- [ ] **Step 3: Write `filters.py`**

```python
"""Decide whether a post is someone hiring, and whether it names the job."""
from __future__ import annotations

import re

_HIRING = [re.compile(p, re.IGNORECASE) for p in (
    r"\bhiring\b",
    r"#\w*hiring\w*",
    r"#job(?:opening|openings|alert|alerts|vacancy|vacancies)\b",
    r"\b(?:job|new|urgent|immediate|multiple|current)\s+openings?\b",
    r"\bopenings?\s+(?:for|in|at)\b",
    r"\bwe have (?:an? )?openings?\b",
    r"\bvacanc(?:y|ies)\b",
    r"\bpositions?\s+(?:open|available)\b",
    r"\bopen\s+(?:positions?|roles?)\b",
    r"\bjoin\s+(?:our|my|the)\s+team\b",
    r"\bapply\s+(?:now|here|today|via|at|through|using)\b",
    r"\b(?:send|share|drop|email|mail)\b[^.\n]{0,30}?\b(?:cv|resume|résumé)s?\b",
    r"\b(?:dm|inbox|message)\s+me\b",
    r"\breferrals?\b",
    r"\bimmediate\s+joiners?\b",
    r"\bwalk[- ]?in\b",
    r"\blooking\s+for\s+(?:an?|talented|candidates|someone|people)\b",
)]

_SEEKER = [re.compile(p, re.IGNORECASE) for p in (
    r"#?\bopen\s?to\s?work\b",
    r"\b(?:i am|i'm|im)\s+(?:actively\s+|currently\s+|now\s+)?(?:looking|seeking|searching)\s+for\s+"
    r"(?:(?:a|an|new|my|next|full[- ]time|part[- ]time)\s+)*(?:job|role|opportunit|position|opening)",
    r"\b(?:i am|i'm|im)\s+(?:actively\s+|currently\s+|now\s+)?seeking\s+"
    r"(?:(?:new|full[- ]time|part[- ]time)\s+)*(?:job|role|opportunit|position)",
    r"\b(?:i am|i'm|im)\s+an?\s+immediate\s+joiner",
)]


def _normalise(text: str) -> str:
    return (text or "").replace("’", "'").replace("‘", "'")


def is_hiring_post(text: str) -> bool:
    """Has hiring language, and doesn't read like the author is the one job hunting."""
    body = _normalise(text)
    if not any(p.search(body) for p in _HIRING):
        return False
    return not any(p.search(body) for p in _SEEKER)


def mentions_title(text: str, job_title: str) -> bool:
    """Every word of the job title starts a word somewhere in the text ('analyst' matches 'Analysts')."""
    words = [w.rstrip(".") for w in re.findall(r"[\w+#.]+", (job_title or "").lower())]
    words = [w for w in words if w]
    body = _normalise(text).lower()
    return bool(words) and all(re.search(r"(?<!\w)" + re.escape(w), body) for w in words)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_filters.py -q`
Expected: all pass. If a phrase fails, adjust the one pattern it hits and rerun; don't loosen `\bhiring\b`.

- [ ] **Step 5: Commit**

```bash
git add peerpatch_linkedin/filters.py tests/test_filters.py
git commit -m "Add hiring and job-seeker filters"
```

---

### Task 3: Chrome plumbing (`browser.py`)

**Files:**
- Create: `peerpatch_linkedin/browser.py`
- Test: `tests/test_browser.py`

**Interfaces:**
- Consumes: `config.*` from Task 1
- Produces:
  - `Say = Callable[[str], None]`
  - `class ScrapeStopped(Exception)`, `class ChromeProblem(Exception)`
  - `@dataclass ScrapeResult(items: list = [], stopped: str | None = None, interrupted: bool = False)`
  - `classify_url(url: str) -> str` returning `"ok"`, `"login"` or `"challenge"`
  - `explain_launch_error(message: str, profile_dir: Path) -> str`
  - `open_chrome(profile_dir: Path)` context manager yielding a Playwright `Page`
  - `is_logged_in(page) -> bool`, `ensure_logged_in(page, say, timeout=None, poll=2.0) -> None`
  - `check_for_walls(page, say, timeout=None, poll=2.0) -> bool` (True if a security check was shown and cleared)
  - `pause(page, seconds: float) -> None`, `polite_wait(page) -> None`
  - `run_extract(page, function_name: str)` runs a function from `extract.js`
  - `save_debug(page, debug_dir: Path | None, name: str) -> None`
  - `first_line(err: BaseException) -> str`

- [ ] **Step 1: Write the failing tests**

`tests/test_browser.py`:
```python
import os

import pytest

from peerpatch_linkedin.browser import classify_url, explain_launch_error, first_line


@pytest.mark.parametrize("url, kind", [
    ("https://www.linkedin.com/feed/", "ok"),
    ("https://www.linkedin.com/search/results/content/?keywords=login", "ok"),
    ("https://www.linkedin.com/jobs/view/signup-specialist-4101234567/", "ok"),
    ("https://www.linkedin.com/login?session_redirect=%2Ffeed%2F", "login"),
    ("https://www.linkedin.com/authwall?trk=bf", "login"),
    ("https://www.linkedin.com/uas/login", "login"),
    ("https://www.linkedin.com/signup/cold-join", "login"),
    ("https://www.linkedin.com/checkpoint/lg/login-submit", "login"),
    ("https://www.linkedin.com/checkpoint/challenge/AgFz", "challenge"),
    ("", "ok"),
])
def test_classify_url(url, kind):
    assert classify_url(url) == kind


def test_missing_chrome_is_explained(tmp_path):
    msg = explain_launch_error("Chromium distribution 'chrome' is not found at /opt/google/chrome/chrome", tmp_path)
    assert "https://www.google.com/chrome/" in msg


def test_profile_in_use_is_explained(tmp_path):
    os.symlink("somehost-1234", tmp_path / "SingletonLock")  # dangling, the way Chrome leaves it
    msg = explain_launch_error("Target page, context or browser has been closed", tmp_path)
    assert "already open" in msg


def test_other_launch_errors_keep_their_first_line(tmp_path):
    assert explain_launch_error("boom\n  at stack", tmp_path) == "Chrome wouldn't start: boom"


def test_first_line():
    assert first_line(RuntimeError("one\ntwo")) == "one"
    assert first_line(RuntimeError("")) == "unknown error"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_browser.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'peerpatch_linkedin.browser'`

- [ ] **Step 3: Write `browser.py`**

```python
"""Everything that touches Chrome: launch, login, walls, waits and in-page scripts."""
from __future__ import annotations

import os
import random
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Callable, Iterator
from urllib.parse import urlparse

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

from . import config

Say = Callable[[str], None]


class ScrapeStopped(Exception):
    """LinkedIn put up a wall we can't get past. The message says which."""


class ChromeProblem(Exception):
    """Chrome wouldn't start. The message tells the person what to do."""


@dataclass
class ScrapeResult:
    items: list = field(default_factory=list)
    stopped: str | None = None
    interrupted: bool = False


def first_line(err: BaseException) -> str:
    text = str(err).strip()
    return text.splitlines()[0] if text else "unknown error"


def classify_url(url: str) -> str:
    segments = [s for s in urlparse(url or "").path.lower().split("/") if s]
    first = segments[0] if segments else ""
    if first in ("login", "authwall", "signup", "uas") or segments[:2] == ["checkpoint", "lg"]:
        return "login"
    if first in ("checkpoint", "challenge"):
        return "challenge"
    return "ok"


def explain_launch_error(message: str, profile_dir: Path) -> str:
    text = message.lower()
    if "is not found" in text or "executable doesn't exist" in text:
        return "Google Chrome isn't installed. Install it from https://www.google.com/chrome/ and run this again."
    if any(os.path.lexists(profile_dir / name) for name in ("SingletonLock", "lockfile")):
        return "Another PeerPatch Chrome window is already open. Close it and run this again."
    return f"Chrome wouldn't start: {first_line(Exception(message))}"


@contextmanager
def open_chrome(profile_dir: Path) -> Iterator:
    profile_dir.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        try:
            context = playwright.chromium.launch_persistent_context(
                str(profile_dir),
                channel="chrome",
                headless=config.HEADLESS,
                no_viewport=not config.HEADLESS,
            )
        except PlaywrightError as err:
            raise ChromeProblem(explain_launch_error(str(err), profile_dir)) from None
        try:
            yield context.pages[0] if context.pages else context.new_page()
        finally:
            try:
                context.close()
            except Exception:
                pass


def pause(page, seconds: float) -> None:
    try:
        page.wait_for_timeout(max(0.0, seconds) * 1000)
    except PlaywrightError:
        raise ScrapeStopped("The Chrome window was closed.") from None


def polite_wait(page) -> None:
    pause(page, random.uniform(config.WAIT_MIN_SECONDS, config.WAIT_MAX_SECONDS))


def is_logged_in(page) -> bool:
    if classify_url(page.url) != "ok":
        return False
    if "/feed" in urlparse(page.url).path:
        return True
    try:
        return any(cookie.get("name") == "li_at" for cookie in page.context.cookies())
    except PlaywrightError:
        return False


def _minutes(seconds: float) -> int:
    return max(1, round(seconds / 60))


def ensure_logged_in(page, say: Say, timeout: float | None = None, poll: float = 2.0) -> None:
    timeout = config.LOGIN_TIMEOUT_SECONDS if timeout is None else timeout
    try:
        page.goto(f"{config.BASE_URL}/feed/", wait_until="domcontentloaded")
    except PlaywrightError as err:
        raise ScrapeStopped(f"Couldn't open LinkedIn: {first_line(err)}") from None
    if is_logged_in(page):
        return
    say(f"Log in to LinkedIn in the Chrome window, then come back here. Waiting up to {_minutes(timeout)} minutes...")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        pause(page, poll)
        if is_logged_in(page):
            say("Logged in.")
            return
    raise ScrapeStopped("No LinkedIn login seen in time. Run this again when you're ready to log in.")


def check_for_walls(page, say: Say, timeout: float | None = None, poll: float = 2.0) -> bool:
    """False if the page is fine. True if a security check appeared and the person solved it.

    Raises ScrapeStopped for a login wall, or a security check that isn't solved in time.
    """
    kind = classify_url(page.url)
    if kind == "ok":
        return False
    if kind == "login":
        raise ScrapeStopped("LinkedIn showed a login wall partway through.")
    timeout = config.CHALLENGE_TIMEOUT_SECONDS if timeout is None else timeout
    say(f"LinkedIn wants a security check. Solve it in the Chrome window. Waiting up to {_minutes(timeout)} minutes...")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        pause(page, poll)
        kind = classify_url(page.url)
        if kind == "ok":
            say("Thanks, carrying on.")
            return True
        if kind == "login":
            raise ScrapeStopped("LinkedIn showed a login wall partway through.")
    raise ScrapeStopped("The security check wasn't solved in time.")


@lru_cache(maxsize=1)
def _extract_js() -> str:
    return Path(__file__).with_name("extract.js").read_text(encoding="utf-8")


def run_extract(page, function_name: str):
    """Run one of the read-only functions in extract.js inside the page and return its result."""
    return page.evaluate("() => {\n" + _extract_js() + "\nreturn " + function_name + "();\n}")


def save_debug(page, debug_dir: Path | None, name: str) -> None:
    if debug_dir is None:
        return
    try:
        debug_dir.mkdir(parents=True, exist_ok=True)
        (debug_dir / f"{name}.html").write_text(page.content(), encoding="utf-8")
    except Exception:
        pass
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_browser.py -q`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add peerpatch_linkedin/browser.py tests/test_browser.py
git commit -m "Add Chrome launch, login and wall handling"
```

---

### Task 4: In-page extraction (`extract.js`) against LinkedIn-shaped markup

**Files:**
- Create: `peerpatch_linkedin/extract.js`
- Modify: `tests/linkedin_markup.py` (add markup builders)
- Create: `tests/conftest.py`, `tests/test_extract.py`

**Interfaces:**
- Consumes: `browser.run_extract` from Task 3
- Produces (JS, called by name through `run_extract`):
  - `peerpatchExtractPosts()` returns a list of `{urn, author, author_headline, author_url, time_label, text, reactions, comments}`
  - `peerpatchExtractJobs()` returns a list of `{job_id, title, company, company_url, location, posted_date, posted_label, salary, benefit}`
  - `peerpatchScrollToBottom()` returns the page height
- Produces (tests): `post_standard(...)`, `post_minimal(...)`, `post_link_only(...)`, `search_page(cards, batch=3)`, `job_card(...)`, `job_card_anchor(...)`; pytest fixtures `browser` and `page`

- [ ] **Step 1: Add markup builders to `tests/linkedin_markup.py`**

Append:
```python
def _e(text: str) -> str:
    return html.escape(text or "")


def _text_html(text: str) -> str:
    return _e(text).replace("\n", "<br>")


def post_standard(urn, author, headline, profile_url, time_label, text, reactions, comments):
    """A post card as it appears in LinkedIn post search results."""
    profile = f"{profile_url}?miniProfileUrn=urn%3Ali%3Afs_miniProfile%3AACoAAB"
    return f"""
<li class="artdeco-card mb2">
  <div data-chameleon-result-urn="{urn}">
    <div class="feed-shared-update-v2 feed-shared-update-v2--minimal-padding full-height relative artdeco-card" data-urn="{urn}" role="article">
      <div class="update-components-actor display-flex">
        <a class="update-components-actor__image relative" href="{profile}"><img alt="View {_e(author)}'s profile" src="data:,"></a>
        <div class="update-components-actor__container">
          <a class="update-components-actor__meta-link" href="{profile}">
            <span class="update-components-actor__title">
              <span class="hoverable-link-text t-14 t-bold"><span dir="ltr"><span aria-hidden="true"><!---->{_e(author)}<!----></span><span class="visually-hidden"><!---->View {_e(author)}'s profile<!----></span></span></span>
            </span>
            <span class="update-components-actor__description text-body-xsmall t-black--light">
              <span aria-hidden="true"><!---->{_e(headline)}<!----></span><span class="visually-hidden"><!---->{_e(headline)}<!----></span>
            </span>
            <span class="update-components-actor__sub-description text-body-xsmall t-black--light">
              <span aria-hidden="true"><!---->{_e(time_label)} • <!----><svg></svg></span><span class="visually-hidden"><!---->{_e(time_label)} ago • Visible to anyone on or off LinkedIn<!----></span>
            </span>
          </a>
        </div>
      </div>
      <div class="feed-shared-update-v2__description-wrapper mr2">
        <div class="feed-shared-inline-show-more-text feed-shared-update-v2__description" tabindex="-1">
          <div class="update-components-text relative update-components-update-v2__commentary" dir="ltr">
            <span class="break-words tvm-parent-container"><span dir="ltr">{_text_html(text)}</span></span>
          </div>
          <button class="feed-shared-inline-show-more-text__see-more-less-toggle see-more t-14" type="button"><span>…more</span></button>
        </div>
      </div>
      <div class="social-details-social-counts">
        <ul class="display-flex">
          <li class="social-details-social-counts__item social-details-social-counts__reactions">
            <button aria-label="{reactions:,} reactions" type="button"><span aria-hidden="true" class="social-details-social-counts__reactions-count">{reactions:,}</span></button>
          </li>
          <li class="social-details-social-counts__item social-details-social-counts__comments">
            <button aria-label="{comments} comments on {_e(author)}'s post" type="button"><span aria-hidden="true">{comments} comments</span></button>
          </li>
        </ul>
      </div>
      <article class="comments-comment-entity" data-id="urn:li:comment:({urn},7400000000000000001)">
        <span dir="ltr">Interested! Sharing my CV.</span>
      </article>
    </div>
  </div>
</li>"""


def post_minimal(urn, company, company_url, text, reactions=0):
    """A stripped-down post card with none of the usual class names. Tests the fallbacks."""
    return f"""
<div role="article" data-id="{urn}">
  <div><a href="{company_url}"><span dir="ltr">{_e(company)}</span></a></div>
  <p><span dir="ltr">{_text_html(text)}</span></p>
  <button aria-label="{reactions} reactions">{reactions}</button>
</div>"""


def post_link_only(urn, author, profile_url, text):
    """A post whose ID only appears in its link. Tests the link fallback."""
    return f"""
<article>
  <a href="{profile_url}">{_e(author)}</a>
  <p>{_text_html(text)}</p>
  <a href="https://www.linkedin.com/feed/update/{urn}/">View post</a>
</article>"""


def search_page(cards, batch=3):
    """Post search results page. Shows `batch` cards, reveals the next batch each time you scroll to the bottom."""
    first = "".join(cards[:batch])
    later = "".join(
        '<template class="more">' + "".join(cards[i:i + batch]) + "</template>"
        for i in range(batch, len(cards), batch)
    )
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Search | LinkedIn</title>
<style>li.artdeco-card, [role=article], article {{ display: block; min-height: 500px; }}</style></head>
<body><main class="scaffold-layout__main"><div class="search-results-container">
<ul class="reusable-search__entity-result-list list-style-none" id="results">{first}</ul>
</div></main>
{later}
<script>
function revealMore() {{
  if (window.innerHeight + window.scrollY < document.documentElement.scrollHeight - 50) return;
  var next = document.querySelector("template.more");
  if (!next) return;
  document.getElementById("results").appendChild(next.content.cloneNode(true));
  next.remove();
}}
window.addEventListener("scroll", revealMore);
window.addEventListener("wheel", function () {{ setTimeout(revealMore, 0); }});
</script>
</body></html>"""


def job_card(job_id, title, company, company_slug, location, date, label, salary="", benefit=""):
    """A job card from LinkedIn's public job listing (div root with a full-card link)."""
    benefit_html = (
        '<div class="job-posting-benefits text-sm"><icon class="job-posting-benefits__icon"></icon>'
        f'<span class="job-posting-benefits__text">{_e(benefit)}</span></div>'
    ) if benefit else ""
    salary_html = f'<span class="job-search-card__salary-info">{_e(salary)}</span>' if salary else ""
    slug = title.lower().replace(" ", "-")
    return f"""
<li>
  <div class="base-card relative w-full hover:no-underline base-card--link base-search-card base-search-card--link job-search-card" data-entity-urn="urn:li:jobPosting:{job_id}" data-impression-id="jobs-search-result-0" data-tracking-id="xyz==">
    <a class="base-card__full-link absolute top-0 right-0 bottom-0 left-0 p-0 z-[2]" href="https://in.linkedin.com/jobs/view/{slug}-at-{company_slug}-{job_id}?position=1&amp;pageNum=0&amp;refId=abc&amp;trackingId=xyz" data-tracking-control-name="public_jobs_jserp-result_search-card">
      <span class="sr-only">
            {_e(title)}
      </span>
    </a>
    <div class="search-entity-media"><img class="artdeco-entity-image" alt="{_e(company)}" src="data:,"></div>
    <div class="base-search-card__info">
      <h3 class="base-search-card__title">
            {_e(title)}
      </h3>
      <h4 class="base-search-card__subtitle">
          <a class="hidden-nested-link" href="https://in.linkedin.com/company/{company_slug}?trk=public_jobs_jserp-result_job-search-card-subtitle">
            {_e(company)}
          </a>
      </h4>
      <div class="base-search-card__metadata">
          <span class="job-search-card__location">
            {_e(location)}
          </span>
          {benefit_html}
          {salary_html}
          <time class="job-search-card__listdate--new" datetime="{date}">
            {_e(label)}
          </time>
      </div>
    </div>
  </div>
</li>"""


def job_card_anchor(job_id, title, company, location, date, label):
    """The other public job card shape: the whole card is one <a>, and the company isn't linked."""
    return f"""
<li>
  <a class="base-card relative w-full base-card--link base-search-card base-search-card--link job-search-card" href="https://www.linkedin.com/jobs/view/{job_id}/?trk=public_jobs" data-entity-urn="urn:li:jobPosting:{job_id}">
    <div class="base-search-card__info">
      <h3 class="base-search-card__title">{_e(title)}</h3>
      <h4 class="base-search-card__subtitle">{_e(company)}</h4>
      <div class="base-search-card__metadata">
        <span class="job-search-card__location">{_e(location)}</span>
        <time class="job-search-card__listdate" datetime="{date}">{_e(label)}</time>
      </div>
    </div>
  </a>
</li>"""
```

- [ ] **Step 2: Write `tests/conftest.py` and the failing tests**

`tests/conftest.py`:
```python
import pytest
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright


@pytest.fixture(scope="session")
def browser():
    with sync_playwright() as playwright:
        try:
            chrome = playwright.chromium.launch(channel="chrome", headless=True)
        except PlaywrightError as err:
            pytest.skip(f"Google Chrome isn't available here: {err}")
        yield chrome
        chrome.close()


@pytest.fixture
def page(browser):
    tab = browser.new_page()
    yield tab
    tab.close()
```

`tests/test_extract.py`:
```python
from datetime import datetime, timezone

from peerpatch_linkedin.browser import run_extract
from tests.linkedin_markup import (
    job_card, job_card_anchor, post_link_only, post_minimal, post_standard, search_page, urn_for,
)

WHEN = datetime(2026, 11, 14, 9, 30, tzinfo=timezone.utc)


def test_reads_all_three_post_shapes(page):
    a, b, c = urn_for(WHEN, salt=1), urn_for(WHEN, "ugcPost", salt=2), urn_for(WHEN, salt=3)
    page.set_content(search_page([
        post_standard(a, "Priya Sharma", "Talent Acquisition at Acme", "https://www.linkedin.com/in/priya-sharma-123",
                      "1d", "We're hiring a Data Analyst!\nDM me.", 1204, 14),
        post_minimal(b, "Acme Analytics", "https://www.linkedin.com/company/acme-analytics/",
                     "Openings for analysts. Apply now.", 52),
        post_link_only(c, "Karan Mehta", "https://www.linkedin.com/in/karan", "Hiring: Data Analyst intern."),
    ], batch=10))

    posts = {p["urn"]: p for p in run_extract(page, "peerpatchExtractPosts")}

    assert set(posts) == {a, b, c}  # the comment inside post `a` is not a post
    assert posts[a] == {
        "urn": a, "author": "Priya Sharma", "author_headline": "Talent Acquisition at Acme",
        "author_url": "https://www.linkedin.com/in/priya-sharma-123", "time_label": "1d •",
        "text": "We're hiring a Data Analyst!\nDM me.", "reactions": 1204, "comments": 14,
    }
    assert posts[b]["author"] == "Acme Analytics"
    assert posts[b]["author_url"] == "https://www.linkedin.com/company/acme-analytics/"
    assert posts[b]["text"] == "Openings for analysts. Apply now."
    assert (posts[b]["reactions"], posts[b]["comments"]) == (52, 0)
    assert posts[c]["author"] == "Karan Mehta"
    assert posts[c]["text"] == "Hiring: Data Analyst intern."


def test_empty_results_page_gives_no_posts(page):
    page.set_content(search_page([]))
    assert run_extract(page, "peerpatchExtractPosts") == []


def test_reads_both_job_card_shapes_and_skips_duplicates(page):
    page.set_content("".join([
        job_card("4101234567", "Data Analyst", "Acme Analytics", "acme-analytics", "Bengaluru, Karnataka, India",
                 "2026-11-14", "1 day ago", salary="₹6,00,000.00 - ₹9,00,000.00", benefit="Actively Hiring"),
        job_card_anchor("4107654321", "Junior Data Analyst", "Zeta Labs", "Pune, Maharashtra, India",
                        "2026-11-10", "5 days ago"),
        job_card("4101234567", "Data Analyst", "Acme Analytics", "acme-analytics", "Bengaluru, Karnataka, India",
                 "2026-11-14", "1 day ago"),
    ]))

    assert run_extract(page, "peerpatchExtractJobs") == [
        {"job_id": "4101234567", "title": "Data Analyst", "company": "Acme Analytics",
         "company_url": "https://in.linkedin.com/company/acme-analytics", "location": "Bengaluru, Karnataka, India",
         "posted_date": "2026-11-14", "posted_label": "1 day ago", "salary": "₹6,00,000.00 - ₹9,00,000.00",
         "benefit": "Actively Hiring"},
        {"job_id": "4107654321", "title": "Junior Data Analyst", "company": "Zeta Labs", "company_url": "",
         "location": "Pune, Maharashtra, India", "posted_date": "2026-11-10", "posted_label": "5 days ago",
         "salary": "", "benefit": ""},
    ]


def test_empty_jobs_page_gives_no_jobs(page):
    page.set_content("")
    assert run_extract(page, "peerpatchExtractJobs") == []
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_extract.py -q`
Expected: FAIL with `FileNotFoundError` for `extract.js`

- [ ] **Step 4: Write `extract.js`**

```javascript
// Read-only scripts that run inside the LinkedIn page. Python calls them through browser.run_extract.
// Nothing here clicks, types or sends anything.

function peerpatchText(el, keepLines) {
  if (!el) return "";
  const copy = el.cloneNode(true);
  copy.querySelectorAll("button, .visually-hidden, script, style, svg").forEach((n) => n.remove());
  if (keepLines) {
    copy.querySelectorAll("br").forEach((br) => br.replaceWith("\n"));
    copy.querySelectorAll("p, li, div").forEach((block) => block.append("\n"));
    return (copy.textContent || "")
      .replace(/[ \t ]+/g, " ")
      .replace(/ *\n */g, "\n")
      .replace(/\n{3,}/g, "\n\n")
      .trim();
  }
  return (copy.textContent || "").replace(/\s+/g, " ").trim();
}

function peerpatchCount(text) {
  const m = (text || "").replace(/,/g, "").match(/(\d+(?:\.\d+)?)\s*([KkMm])?/);
  if (!m) return 0;
  let n = parseFloat(m[1]);
  if (m[2]) n *= m[2].toLowerCase() === "k" ? 1000 : 1000000;
  return Math.round(n);
}

function peerpatchPick(root, selectors) {
  for (const s of selectors) {
    const el = root.querySelector(s);
    if (el) return el;
  }
  return null;
}

function peerpatchCleanUrl(href) {
  if (!href) return "";
  try {
    const u = new URL(href, location.href);
    return u.origin + u.pathname;
  } catch (e) {
    return "";
  }
}

function peerpatchExtractPosts() {
  const exact = /^urn:li:(?:activity|share|ugcPost):\d{15,20}$/;
  const loose = /urn:li:(?:activity|share|ugcPost):\d{15,20}/;
  const found = new Map(); // urn -> container element

  for (const el of document.querySelectorAll("[data-urn], [data-chameleon-result-urn], [data-id]")) {
    for (const name of ["data-urn", "data-chameleon-result-urn", "data-id"]) {
      const value = el.getAttribute(name);
      if (value && exact.test(value)) {
        if (!found.has(value)) found.set(value, el);
        break;
      }
    }
  }

  const linkSelector = 'a[href*="urn:li:activity:"], a[href*="urn:li:ugcPost:"], a[href*="urn:li:share:"], a[href*="urn%3Ali%3A"]';
  for (const a of document.querySelectorAll(linkSelector)) {
    if ([...found.values()].some((box) => box.contains(a))) continue;
    let href = a.getAttribute("href") || "";
    try { href = decodeURIComponent(href); } catch (e) { /* keep raw */ }
    const m = href.match(loose);
    if (!m || found.has(m[0])) continue;
    const box = a.closest('[role="article"], article, li') || a.parentElement;
    if (box) found.set(m[0], box);
  }

  const posts = [];
  for (const [urn, box] of found) {
    const actorLink = peerpatchPick(box, [
      "a.update-components-actor__meta-link", "a.update-components-actor__image",
      'a[href*="/in/"]', 'a[href*="/company/"]', 'a[href*="/school/"]',
    ]);
    let author = peerpatchText(peerpatchPick(box, [".update-components-actor__title", ".update-components-actor__name"]));
    if (!author && actorLink) author = peerpatchText(actorLink).slice(0, 100);

    let textEl = peerpatchPick(box, [
      ".update-components-text", ".feed-shared-inline-show-more-text", ".feed-shared-text", '[class*="commentary"]',
    ]);
    if (!textEl) {
      let bestLen = 0;
      for (const el of box.querySelectorAll('span[dir="ltr"], p')) {
        const len = (el.textContent || "").trim().length;
        if (len > bestLen) { textEl = el; bestLen = len; }
      }
    }

    let reactions = 0;
    let comments = 0;
    const reactionCount = box.querySelector(".social-details-social-counts__reactions-count");
    if (reactionCount) reactions = peerpatchCount(reactionCount.textContent);
    for (const el of box.querySelectorAll("[aria-label]")) {
      const label = el.getAttribute("aria-label") || "";
      const r = label.match(/^([\d.,]+[KkMm]?)\s+reactions?\b/i);
      const c = label.match(/^([\d.,]+[KkMm]?)\s+comments?\b/i);
      if (r && !reactions) reactions = peerpatchCount(r[1]);
      if (c && !comments) comments = peerpatchCount(c[1]);
    }

    posts.push({
      urn,
      author,
      author_headline: peerpatchText(peerpatchPick(box, [".update-components-actor__description"])),
      author_url: actorLink ? peerpatchCleanUrl(actorLink.href) : "",
      time_label: peerpatchText(peerpatchPick(box, [".update-components-actor__sub-description"])),
      text: peerpatchText(textEl, true),
      reactions,
      comments,
    });
  }
  return posts;
}

function peerpatchExtractJobs() {
  const jobs = [];
  const seen = new Set();
  const cards = document.querySelectorAll('[data-entity-urn^="urn:li:jobPosting:"], .base-search-card, .job-search-card');
  for (const card of cards) {
    const holder = card.closest('[data-entity-urn^="urn:li:jobPosting:"]') || card.querySelector('[data-entity-urn^="urn:li:jobPosting:"]');
    const link = card.matches("a") ? card : card.querySelector('a.base-card__full-link, a[href*="/jobs/view/"]');
    let id = "";
    const urnMatch = ((holder && holder.getAttribute("data-entity-urn")) || "").match(/urn:li:jobPosting:(\d+)/);
    if (urnMatch) id = urnMatch[1];
    if (!id && link) {
      const hrefMatch = (link.getAttribute("href") || "").match(/\/jobs\/view\/(?:[^/?#]*?-)?(\d{6,})/);
      if (hrefMatch) id = hrefMatch[1];
    }
    if (!id || seen.has(id)) continue;
    seen.add(id);

    const read = (selector) => peerpatchText(card.querySelector(selector));
    const time = card.querySelector("time");
    const companyLink = card.querySelector(".base-search-card__subtitle a");
    jobs.push({
      job_id: id,
      title: read(".base-search-card__title") || peerpatchText(link),
      company: read(".base-search-card__subtitle"),
      company_url: companyLink ? peerpatchCleanUrl(companyLink.href) : "",
      location: read(".job-search-card__location"),
      posted_date: time ? time.getAttribute("datetime") || "" : "",
      posted_label: peerpatchText(time),
      salary: read(".job-search-card__salary-info"),
      benefit: read(".job-posting-benefits__text"),
    });
  }
  return jobs;
}

function peerpatchScrollToBottom() {
  window.scrollTo(0, document.documentElement.scrollHeight);
  for (const el of document.querySelectorAll("main, .scaffold-layout__main, .scaffold-finite-scroll, #workspace")) {
    if (el.scrollHeight > el.clientHeight + 10) el.scrollTop = el.scrollHeight;
  }
  return document.documentElement.scrollHeight;
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_extract.py -q`
Expected: all pass (or skipped with "Google Chrome isn't available here" on a machine without Chrome)

- [ ] **Step 6: Commit**

```bash
git add peerpatch_linkedin/extract.js tests/linkedin_markup.py tests/conftest.py tests/test_extract.py
git commit -m "Add in-page extraction for posts and job cards"
```

---

### Task 5: Posts (`posts.py`)

**Files:**
- Create: `peerpatch_linkedin/posts.py`
- Test: `tests/test_posts.py`

**Interfaces:**
- Consumes: `browser.ScrapeResult, ScrapeStopped, Say, check_for_walls, polite_wait, run_extract, save_debug, first_line`; `filters.is_hiring_post, mentions_title`; `timeparse.urn_to_datetime, relative_label_to_hours`
- Produces:
  - `@dataclass Post(urn, posted_at: datetime, author, author_headline, author_url, text, reactions: int, comments: int, mentions_title: bool)` with `.url -> str` and `.hours_ago(now) -> float`
  - `build_search_url(job: str) -> str`
  - `to_post(raw: dict, job: str, now: datetime) -> Post | None`
  - `select_posts(raws: list[dict], job: str, now: datetime, max_hours: float) -> tuple[list[Post], float | None]`
  - `scrape_posts(page, job: str, *, say, max_hours=48, max_posts=100, debug_dir=None, now=None) -> ScrapeResult` (items are `Post`, newest first)

- [ ] **Step 1: Write the failing tests**

`tests/test_posts.py`:
```python
from datetime import datetime, timedelta, timezone

from peerpatch_linkedin import config
from peerpatch_linkedin.posts import build_search_url, select_posts, to_post
from tests.linkedin_markup import urn_for

NOW = datetime(2026, 11, 15, 12, 0, tzinfo=timezone.utc)


def raw(hours_ago, text, salt=1, **extra):
    base = {"urn": urn_for(NOW - timedelta(hours=hours_ago), salt=salt), "author": "A", "author_headline": "",
            "author_url": "", "time_label": "", "text": text, "reactions": 0, "comments": 0}
    base.update(extra)
    return base


def test_search_url_quotes_title_and_asks_for_latest_past_week(monkeypatch):
    monkeypatch.setattr(config, "BASE_URL", "https://www.linkedin.com")
    assert build_search_url("data analyst") == (
        "https://www.linkedin.com/search/results/content/?keywords=%22data%20analyst%22%20hiring"
        "&datePosted=%22past-week%22&sortBy=%22date_posted%22"
    )


def test_search_url_handles_quotes_plus_ampersand_and_hindi():
    assert "keywords=%22sales%22%20hiring" in build_search_url('  "sales" ')
    assert "keywords=%22C%2B%2B%20developer%22%20hiring" in build_search_url("C++ developer")
    assert "keywords=%22R%26D%20engineer%22%20hiring" in build_search_url("R&D engineer")
    assert "keywords=%22%E0%A4" in build_search_url("डेटा विश्लेषक")


def test_keeps_recent_hiring_posts_and_reports_oldest():
    raws = [
        raw(1, "We're hiring a data analyst", salt=1),
        raw(20, "SQL tips for data analysts", salt=2),
        raw(30, "I'm looking for a new role. #opentowork", salt=3),
        raw(47.9, "Hiring now, DM me", salt=4),
        raw(50, "Hiring now", salt=5),
    ]
    kept, oldest = select_posts(raws, "data analyst", NOW, 48)
    assert [round(p.hours_ago(NOW), 1) for p in kept] == [1.0, 47.9]
    assert [p.mentions_title for p in kept] == [True, False]
    assert round(oldest) == 50


def test_falls_back_to_time_label_when_id_has_no_time():
    post = to_post({"urn": "urn:li:activity:12345", "time_label": "3h • Edited", "text": "We are hiring"}, "x", NOW)
    assert post.posted_at == NOW - timedelta(hours=3)


def test_posts_without_time_or_text_are_handled_quietly():
    assert to_post({"urn": "", "time_label": "", "text": ""}, "x", NOW) is None
    kept, oldest = select_posts([raw(2, "")], "x", NOW, 48)
    assert kept == [] and round(oldest) == 2


def test_post_link_always_points_at_linkedin(monkeypatch):
    monkeypatch.setattr(config, "BASE_URL", "http://127.0.0.1:9999")
    post = to_post(raw(1, "hiring"), "x", NOW)
    assert post.url == f"https://www.linkedin.com/feed/update/{post.urn}/"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_posts.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'peerpatch_linkedin.posts'`

- [ ] **Step 3: Write `posts.py`**

```python
"""Hiring posts from LinkedIn post search."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote, urlencode

from playwright.sync_api import Error as PlaywrightError

from . import config
from .browser import (
    ScrapeResult, ScrapeStopped, Say, check_for_walls, first_line, polite_wait, run_extract, save_debug,
)
from .filters import is_hiring_post
from .filters import mentions_title as _mentions_title
from .timeparse import relative_label_to_hours, urn_to_datetime

_LOAD_MORE = "button.scaffold-finite-scroll__load-button, button:has-text('Show more results')"


@dataclass
class Post:
    urn: str
    posted_at: datetime
    author: str
    author_headline: str
    author_url: str
    text: str
    reactions: int
    comments: int
    mentions_title: bool

    @property
    def url(self) -> str:
        return f"{config.PUBLIC_URL}/feed/update/{self.urn}/"

    def hours_ago(self, now: datetime) -> float:
        return (now - self.posted_at).total_seconds() / 3600


def _clean_title(job: str) -> str:
    return (job or "").strip().strip('"“”').strip()


def build_search_url(job: str) -> str:
    params = {"keywords": f'"{_clean_title(job)}" hiring', "datePosted": '"past-week"', "sortBy": '"date_posted"'}
    return f"{config.BASE_URL}/search/results/content/?{urlencode(params, quote_via=quote)}"


def to_post(raw: dict, job: str, now: datetime) -> Post | None:
    urn = raw.get("urn") or ""
    posted = urn_to_datetime(urn)
    if posted is None:
        hours = relative_label_to_hours(raw.get("time_label") or "")
        if hours is None:
            return None
        posted = now - timedelta(hours=hours)
    text = raw.get("text") or ""
    return Post(
        urn=urn,
        posted_at=posted,
        author=raw.get("author") or "",
        author_headline=raw.get("author_headline") or "",
        author_url=raw.get("author_url") or "",
        text=text,
        reactions=int(raw.get("reactions") or 0),
        comments=int(raw.get("comments") or 0),
        mentions_title=_mentions_title(text, job),
    )


def select_posts(raws: list[dict], job: str, now: datetime, max_hours: float) -> tuple[list[Post], float | None]:
    """Keep recent hiring posts. Also return the age of the oldest post seen, so the caller knows when to stop."""
    kept: list[Post] = []
    oldest: float | None = None
    for raw in raws:
        post = to_post(raw, job, now)
        if post is None:
            continue
        age = post.hours_ago(now)
        oldest = age if oldest is None else max(oldest, age)
        if age <= max_hours and is_hiring_post(post.text):
            kept.append(post)
    return kept, oldest


def _load_more(page) -> None:
    run_extract(page, "peerpatchScrollToBottom")
    try:
        page.mouse.move(600, 500)
        page.mouse.wheel(0, 4000)
        button = page.locator(_LOAD_MORE).first
        if button.is_visible():
            button.click(timeout=3000)
    except PlaywrightError:
        pass


def scrape_posts(page, job: str, *, say: Say, max_hours: float = 48, max_posts: int = 100,
                 debug_dir: Path | None = None, now: datetime | None = None) -> ScrapeResult:
    now = now or datetime.now(timezone.utc)
    kept: dict[str, Post] = {}
    seen: set[str] = set()

    def result(stopped: str | None = None, interrupted: bool = False) -> ScrapeResult:
        posts = sorted(kept.values(), key=lambda p: p.posted_at, reverse=True)[:max_posts]
        return ScrapeResult(posts, stopped, interrupted)

    try:
        url = build_search_url(job)
        page.goto(url, wait_until="domcontentloaded")
        if check_for_walls(page, say):
            page.goto(url, wait_until="domcontentloaded")
            check_for_walls(page, say)
        polite_wait(page)
        stale_rounds = 0
        for _ in range(config.MAX_SCROLLS):
            raws = run_extract(page, "peerpatchExtractPosts")
            new_urns = {r["urn"] for r in raws} - seen
            seen |= new_urns
            posts, oldest = select_posts(raws, job, now, max_hours)
            for post in posts:
                kept.setdefault(post.urn, post)
            say(f"  Posts: {len(seen)} looked at, {len(kept)} hiring posts kept")
            if len(kept) >= max_posts or (oldest is not None and oldest > max_hours):
                break
            stale_rounds = 0 if new_urns else stale_rounds + 1
            if stale_rounds >= 2:
                break
            _load_more(page)
            polite_wait(page)
            check_for_walls(page, say)
        save_debug(page, debug_dir, "posts")
    except ScrapeStopped as stop:
        save_debug(page, debug_dir, "posts-stopped")
        return result(str(stop))
    except PlaywrightError as err:
        return result(f"Chrome had a problem during the post search: {first_line(err)}")
    except KeyboardInterrupt:
        return result("Stopped with Ctrl+C.", interrupted=True)
    return result()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_posts.py -q`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add peerpatch_linkedin/posts.py tests/test_posts.py
git commit -m "Add post search, time cutoff and scrolling"
```

---

### Task 6: Jobs (`jobs.py`)

**Files:**
- Create: `peerpatch_linkedin/jobs.py`
- Test: `tests/test_jobs.py`

**Interfaces:**
- Consumes: `browser.ScrapeResult, ScrapeStopped, Say, check_for_walls, first_line, pause, polite_wait, run_extract, save_debug`
- Produces:
  - `@dataclass Job(job_id, title, company, company_url, location, posted_date, posted_label, salary, benefit)` (all `str`) with `.url -> str`
  - `build_jobs_url(job: str, location: str, days: int, start: int) -> str`
  - `to_job(raw: dict) -> Job`
  - `status_problem(status: int) -> str | None` (`"retry"` for 429, a message for 999, else `None`)
  - `scrape_jobs(page, job: str, location: str, *, say, days=7, max_jobs=200, debug_dir=None) -> ScrapeResult` (items are `Job`, in LinkedIn's order)

- [ ] **Step 1: Write the failing tests**

`tests/test_jobs.py`:
```python
from peerpatch_linkedin import config
from peerpatch_linkedin.jobs import build_jobs_url, status_problem, to_job


def test_jobs_url_is_past_week_newest_first(monkeypatch):
    monkeypatch.setattr(config, "BASE_URL", "https://www.linkedin.com")
    assert build_jobs_url("data analyst", "Bengaluru", 7, 0) == (
        "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
        "?keywords=data%20analyst&location=Bengaluru&f_TPR=r604800&sortBy=DD&start=0"
    )


def test_jobs_url_without_location_and_with_odd_titles():
    url = build_jobs_url('"C++ developer"', "   ", 3, 25)
    assert "location=" not in url
    assert "keywords=C%2B%2B%20developer" in url
    assert "f_TPR=r259200" in url
    assert url.endswith("start=25")
    assert "keywords=%E0%A4" in build_jobs_url("डेटा विश्लेषक", "India", 7, 0)
    assert "keywords=R%26D" in build_jobs_url("R&D", "India", 7, 0)


def test_to_job_fills_blanks_and_builds_link(monkeypatch):
    monkeypatch.setattr(config, "BASE_URL", "http://127.0.0.1:9999")
    job = to_job({"job_id": "4101234567", "title": "Data Analyst", "salary": None})
    assert job.url == "https://www.linkedin.com/jobs/view/4101234567/"
    assert (job.salary, job.company) == ("", "")


def test_status_problem():
    assert status_problem(200) is None
    assert status_problem(400) is None  # LinkedIn's "no more results"
    assert status_problem(429) == "retry"
    assert "999" in status_problem(999)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_jobs.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'peerpatch_linkedin.jobs'`

- [ ] **Step 3: Write `jobs.py`**

```python
"""Job listings from LinkedIn's public job search."""
from __future__ import annotations

from dataclasses import dataclass, fields
from pathlib import Path
from urllib.parse import quote, urlencode

from playwright.sync_api import Error as PlaywrightError

from . import config
from .browser import (
    ScrapeResult, ScrapeStopped, Say, check_for_walls, first_line, pause, polite_wait, run_extract, save_debug,
)


@dataclass
class Job:
    job_id: str
    title: str
    company: str
    company_url: str
    location: str
    posted_date: str
    posted_label: str
    salary: str
    benefit: str

    @property
    def url(self) -> str:
        return f"{config.PUBLIC_URL}/jobs/view/{self.job_id}/"


def build_jobs_url(job: str, location: str, days: int, start: int) -> str:
    params = {"keywords": (job or "").strip().strip('"“”').strip()}
    if (location or "").strip():
        params["location"] = location.strip()
    params.update({"f_TPR": f"r{int(days) * 86400}", "sortBy": "DD", "start": str(int(start))})
    return f"{config.BASE_URL}/jobs-guest/jobs/api/seeMoreJobPostings/search?{urlencode(params, quote_via=quote)}"


def to_job(raw: dict) -> Job:
    return Job(**{f.name: str(raw.get(f.name) or "") for f in fields(Job)})


def status_problem(status: int) -> str | None:
    if status == 429:
        return "retry"
    if status == 999:
        return "LinkedIn refused the jobs search (HTTP 999). That usually clears in a few hours."
    return None


def scrape_jobs(page, job: str, location: str, *, say: Say, days: int = 7, max_jobs: int = 200,
                debug_dir: Path | None = None) -> ScrapeResult:
    found: dict[str, Job] = {}

    def result(stopped: str | None = None, interrupted: bool = False) -> ScrapeResult:
        return ScrapeResult(list(found.values())[:max_jobs], stopped, interrupted)

    start = 0
    retried = False
    try:
        for page_number in range(1, config.MAX_JOB_PAGES + 1):
            response = page.goto(build_jobs_url(job, location, days, start), wait_until="domcontentloaded")
            problem = status_problem(response.status if response else 200)
            if problem == "retry":
                if retried:
                    return result("LinkedIn is rate-limiting the jobs search (HTTP 429). Try again in an hour.")
                retried = True
                say(f"  Jobs: LinkedIn asked us to slow down. Waiting {int(config.RATE_LIMIT_PAUSE_SECONDS)} seconds...")
                pause(page, config.RATE_LIMIT_PAUSE_SECONDS)
                continue
            if problem:
                return result(problem)
            retried = False
            if check_for_walls(page, say):
                continue  # security check solved: load the same page again
            save_debug(page, debug_dir, f"jobs-{page_number:02d}")
            raws = run_extract(page, "peerpatchExtractJobs")
            fresh = 0
            for raw in raws:
                item = to_job(raw)
                if item.job_id and item.job_id not in found:
                    found[item.job_id] = item
                    fresh += 1
            say(f"  Jobs: page {page_number}, {len(found)} found")
            if not raws or fresh == 0 or len(found) >= max_jobs:
                break
            start += len(raws)
            polite_wait(page)
    except ScrapeStopped as stop:
        return result(str(stop))
    except PlaywrightError as err:
        return result(f"Chrome had a problem during the jobs search: {first_line(err)}")
    except KeyboardInterrupt:
        return result("Stopped with Ctrl+C.", interrupted=True)
    return result()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_jobs.py -q`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add peerpatch_linkedin/jobs.py tests/test_jobs.py
git commit -m "Add public job listing search with paging and rate-limit handling"
```

---

### Task 7: Output files (`report.py`)

**Files:**
- Create: `peerpatch_linkedin/report.py`
- Test: `tests/test_report.py`

**Interfaces:**
- Consumes: duck-typed `Post` and `Job` objects (attributes from Tasks 5 and 6). `report.py` imports neither module.
- Produces:
  - `POST_COLUMNS: list[str]`, `JOB_COLUMNS: list[str]`
  - `results_dir(root: Path, job: str, location: str, when: datetime) -> Path` (not created)
  - `excel_safe(value) -> str`, `safe_url(url: str) -> str`
  - `post_row(post, now) -> dict`, `job_row(job) -> dict`, `write_csv(path, columns, rows) -> None`
  - `render_report(*, job, location, run_at, post_hours, job_days, posts, jobs, now, notes) -> str`
  - `write_results(out_dir, *, job, location, run_at, post_hours, job_days, posts, jobs, now, notes) -> Path` (path of `report.html`)

- [ ] **Step 1: Write the failing tests**

`tests/test_report.py`:
```python
import csv
import io
from datetime import datetime, timedelta, timezone

from peerpatch_linkedin.jobs import to_job
from peerpatch_linkedin.posts import Post
from peerpatch_linkedin.report import (
    POST_COLUMNS, excel_safe, post_row, render_report, results_dir, write_csv, write_results,
)

NOW = datetime(2026, 11, 15, 12, 0, tzinfo=timezone.utc)


def make_post(**changes):
    values = dict(urn="urn:li:activity:7000000000000000001", posted_at=NOW - timedelta(hours=5),
                  author="Priya Sharma", author_headline="Recruiter", author_url="https://www.linkedin.com/in/priya",
                  text="We're hiring", reactions=3, comments=1, mentions_title=True)
    values.update(changes)
    return Post(**values)


def render(**changes):
    args = dict(job="data analyst", location="Bengaluru", run_at=NOW, post_hours=48, job_days=7,
                posts=[], jobs=[], now=NOW, notes=[])
    args.update(changes)
    return render_report(**args)


def test_results_dir_name_and_same_minute_rerun(tmp_path):
    when = datetime(2026, 11, 15, 10, 30)
    first = results_dir(tmp_path, "Data Analyst", "Bengaluru", when)
    assert first.name == "data-analyst_bengaluru_2026-11-15_1030"
    first.mkdir()
    assert results_dir(tmp_path, "Data Analyst", "Bengaluru", when).name == "data-analyst_bengaluru_2026-11-15_1030-2"


def test_results_dir_for_titles_without_latin_letters(tmp_path):
    assert results_dir(tmp_path, "डेटा विश्लेषक", "", datetime(2026, 11, 15, 10, 30)).name == "search_2026-11-15_1030"


def test_csv_has_bom_and_keeps_rupee_and_line_breaks(tmp_path):
    path = tmp_path / "posts.csv"
    write_csv(path, POST_COLUMNS, [post_row(make_post(text="Line one\nCTC ₹12 LPA"), NOW)])
    data = path.read_bytes()
    assert data.startswith(b"\xef\xbb\xbf")
    row = next(csv.DictReader(io.StringIO(data.decode("utf-8-sig"))))
    assert row["text"] == "Line one\nCTC ₹12 LPA"
    assert row["hours_ago"] == "5.0"
    assert row["mentions_title"] == "yes"
    assert row["post_url"] == "https://www.linkedin.com/feed/update/urn:li:activity:7000000000000000001/"


def test_excel_formulas_are_neutralised():
    assert excel_safe('=HYPERLINK("http://x")') == '\'=HYPERLINK("http://x")'
    assert excel_safe("+91 98765 43210") == "'+91 98765 43210"
    assert excel_safe("@channel") == "'@channel"
    assert excel_safe("-2+3") == "'-2+3"
    assert excel_safe("- bullet point") == "- bullet point"
    assert excel_safe(52) == "52"
    assert excel_safe(None) == ""


def test_report_escapes_text_and_drops_unsafe_links():
    job = to_job({"job_id": "1", "title": "Analyst <b>", "company": "Acme",
                  "company_url": "https://in.linkedin.com/company/acme"})
    page = render(posts=[make_post(text="<script>alert(1)</script> hiring", author_url="javascript:alert(1)")],
                  jobs=[job], notes=["Post search stopped early: test"])
    assert "<script>alert(1)" not in page
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page
    assert "javascript:" not in page
    assert "Analyst &lt;b&gt;" in page
    assert "Hiring posts (1)" in page and "Jobs (1)" in page
    assert "Post search stopped early: test" in page
    assert 'href="https://www.linkedin.com/jobs/view/1/"' in page


def test_long_posts_fold_behind_more_and_empty_sections_say_so():
    page = render(posts=[make_post(text="word " * 200)])
    assert "<details><summary>more</summary>" in page
    assert "No jobs found." in render()
    assert "No hiring posts found." in render()


def test_write_results_creates_three_files(tmp_path):
    report = write_results(tmp_path / "out", job="data analyst", location="", run_at=NOW, post_hours=48,
                           job_days=7, posts=[make_post()], jobs=[], now=NOW, notes=[])
    assert report.name == "report.html"
    assert sorted(p.name for p in (tmp_path / "out").iterdir()) == ["jobs.csv", "posts.csv", "report.html"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_report.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'peerpatch_linkedin.report'`

- [ ] **Step 3: Write `report.py`**

```python
"""Write results: two CSVs and one self-contained HTML page. Knows nothing about browsers."""
from __future__ import annotations

import csv
import html
import re
from datetime import datetime
from pathlib import Path
from string import Template

POST_COLUMNS = ["posted_at", "hours_ago", "author", "author_headline", "author_url", "mentions_title",
                "reactions", "comments", "post_url", "text"]
JOB_COLUMNS = ["posted_date", "posted_label", "title", "company", "location", "salary", "benefit",
               "job_url", "company_url", "job_id"]


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")[:40].strip("-")


def results_dir(root: Path, job: str, location: str, when: datetime) -> Path:
    name = "_".join(part for part in (_slug(job), _slug(location)) if part) or "search"
    name = f"{name}_{when.strftime('%Y-%m-%d_%H%M')}"
    candidate, n = root / name, 2
    while candidate.exists():
        candidate, n = root / f"{name}-{n}", n + 1
    return candidate


def excel_safe(value) -> str:
    """Stop Excel from treating a cell as a formula."""
    text = "" if value is None else str(value)
    if text[:1] in ("=", "+", "@", "\t", "\r") or (text[:1] == "-" and text[1:2] not in ("", " ")):
        return "'" + text
    return text


def safe_url(url: str) -> str:
    return url if re.match(r"^https?://", url or "", re.IGNORECASE) else ""


def post_row(post, now: datetime) -> dict:
    return {
        "posted_at": post.posted_at.astimezone().strftime("%Y-%m-%d %H:%M"),
        "hours_ago": f"{post.hours_ago(now):.1f}",
        "author": post.author,
        "author_headline": post.author_headline,
        "author_url": post.author_url,
        "mentions_title": "yes" if post.mentions_title else "no",
        "reactions": post.reactions,
        "comments": post.comments,
        "post_url": post.url,
        "text": post.text,
    }


def job_row(job) -> dict:
    return {
        "posted_date": job.posted_date, "posted_label": job.posted_label, "title": job.title,
        "company": job.company, "location": job.location, "salary": job.salary, "benefit": job.benefit,
        "job_url": job.url, "company_url": job.company_url, "job_id": job.job_id,
    }


def write_csv(path: Path, columns: list[str], rows: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: excel_safe(row.get(key, "")) for key in columns})


def _ago(hours: float) -> str:
    if hours < 1:
        return f"{max(1, round(hours * 60))} min ago"
    if hours < 48:
        return f"{round(hours)} h ago"
    return f"{round(hours / 24)} days ago"


def _split_text(text: str, limit: int = 300) -> tuple[str, str]:
    if len(text) <= limit:
        return text, ""
    cut = text.rfind(" ", 0, limit)
    if cut < limit // 2:
        cut = limit
    return text[:cut].rstrip() + "…", text[cut:].strip()


def _link(url: str, label: str, css: str = "") -> str:
    e = html.escape
    url = safe_url(url)
    css_attr = f' class="{css}"' if css else ""
    if not url:
        return f"<span{css_attr}>{e(label)}</span>"
    return f'<a{css_attr} href="{e(url)}" target="_blank" rel="noopener">{e(label)}</a>'


def _post_card(post, now: datetime) -> str:
    e = html.escape
    first, rest = _split_text(post.text)
    more = f'<details><summary>more</summary><div class="text">{e(rest)}</div></details>' if rest else ""
    tag = '<span class="tag">names the job</span>' if post.mentions_title else ""
    words = e(" ".join([post.author, post.author_headline, post.text]).lower())
    return (
        f'<article class="post" data-filter="{words}"><header>'
        f'{_link(post.author_url, post.author or "Unknown", "author")}'
        f'<span class="headline">{e(post.author_headline)}</span>'
        f'<span class="when">{_ago(post.hours_ago(now))}</span>{tag}</header>'
        f'<div class="text">{e(first)}</div>{more}'
        f'<p class="foot">{_link(post.url, "Open post")} '
        f'<span class="when">{post.reactions} reactions, {post.comments} comments</span></p></article>'
    )


def _jobs_table(jobs) -> str:
    e = html.escape
    if not jobs:
        return '<p class="empty">No jobs found.</p>'
    rows = []
    for job in jobs:
        words = e(" ".join([job.title, job.company, job.location, job.salary]).lower())
        rows.append(
            f'<tr data-filter="{words}"><td>{_link(job.url, job.title or "Untitled")}</td>'
            f"<td>{_link(job.company_url, job.company)}</td><td>{e(job.location)}</td>"
            f"<td>{e(job.posted_label or job.posted_date)}</td><td>{e(job.salary)}</td></tr>"
        )
    return (
        '<div class="table-wrap"><table><thead><tr><th>Title</th><th>Company</th><th>Location</th>'
        "<th>Posted</th><th>Salary</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>"
    )


_PAGE = Template("""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>$title</title>
<style>
:root { --bg: #f7f6f2; --card: #ffffff; --text: #1d1d1b; --muted: #6b6a66; --line: #e2e0d9; --accent: #0a66c2; --tag: #e8f1fb; }
@media (prefers-color-scheme: dark) {
  :root { --bg: #161615; --card: #20201e; --text: #ecebe6; --muted: #a3a29c; --line: #34332f; --accent: #70b5f9; --tag: #1d2c3d; }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--text); font: 15px/1.5 -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
main { max-width: 980px; margin: 0 auto; padding: 24px 16px 64px; }
h1 { font-size: 24px; margin: 0 0 4px; }
h2 { font-size: 18px; margin: 32px 0 12px; }
.meta { color: var(--muted); margin: 0 0 16px; }
.note { background: var(--tag); border-radius: 8px; padding: 10px 12px; margin: 8px 0; }
input[type=search] { width: 100%; padding: 10px 12px; font: inherit; border: 1px solid var(--line); border-radius: 8px; background: var(--card); color: var(--text); }
.post { background: var(--card); border: 1px solid var(--line); border-radius: 10px; padding: 14px 16px; margin: 0 0 12px; }
.post header { display: flex; flex-wrap: wrap; gap: 4px 10px; align-items: baseline; }
.author { font-weight: 600; }
.headline, .when { color: var(--muted); font-size: 13px; }
.tag { background: var(--tag); color: var(--accent); border-radius: 999px; padding: 1px 8px; font-size: 12px; }
.text { white-space: pre-line; margin: 8px 0; overflow-wrap: anywhere; }
.foot { margin: 8px 0 0; }
details summary { cursor: pointer; color: var(--accent); }
a { color: var(--accent); }
.table-wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; background: var(--card); border: 1px solid var(--line); }
th, td { text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--line); vertical-align: top; }
th { font-size: 13px; color: var(--muted); font-weight: 600; }
.empty { color: var(--muted); }
</style>
</head>
<body>
<main>
<h1>$heading</h1>
<p class="meta">$meta</p>
$notes
<input type="search" id="filter" placeholder="Filter posts and jobs" aria-label="Filter posts and jobs">
<h2>Hiring posts ($post_count)</h2>
$posts
<h2>Jobs ($job_count)</h2>
$jobs
</main>
<script>
document.getElementById("filter").addEventListener("input", function (event) {
  var query = event.target.value.toLowerCase();
  document.querySelectorAll("[data-filter]").forEach(function (item) {
    item.hidden = query !== "" && item.getAttribute("data-filter").indexOf(query) === -1;
  });
});
</script>
</body>
</html>
""")


def render_report(*, job, location, run_at, post_hours, job_days, posts, jobs, now, notes) -> str:
    e = html.escape
    where = f" in {location}" if location else ""
    posts_html = "".join(_post_card(p, now) for p in posts) or '<p class="empty">No hiring posts found.</p>'
    return _PAGE.substitute(
        title=e(f"{job} jobs{where}"),
        heading=e(f"{job}{where}"),
        meta=e(f"Run {run_at.astimezone().strftime('%d %b %Y, %H:%M')}. "
               f"Posts from the last {post_hours} hours, jobs from the last {job_days} days."),
        notes="".join(f'<p class="note">{e(n)}</p>' for n in notes),
        post_count=len(posts),
        posts=posts_html,
        job_count=len(jobs),
        jobs=_jobs_table(jobs),
    )


def write_results(out_dir: Path, *, job, location, run_at, post_hours, job_days, posts, jobs, now, notes) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(out_dir / "posts.csv", POST_COLUMNS, [post_row(p, now) for p in posts])
    write_csv(out_dir / "jobs.csv", JOB_COLUMNS, [job_row(j) for j in jobs])
    report = out_dir / "report.html"
    report.write_text(
        render_report(job=job, location=location, run_at=run_at, post_hours=post_hours, job_days=job_days,
                      posts=posts, jobs=jobs, now=now, notes=notes),
        encoding="utf-8",
    )
    return report
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_report.py -q`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add peerpatch_linkedin/report.py tests/test_report.py
git commit -m "Add CSV and HTML report writers"
```

---

### Task 8: Command line (`cli.py`, `__main__.py`)

**Files:**
- Create: `peerpatch_linkedin/cli.py`, `peerpatch_linkedin/__main__.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: everything above
- Produces: `parse_args(argv) -> Namespace`, `resolve_search(args, ask) -> tuple[str, str]`, `clamp_limits(args, say) -> None`, `make_console_safe(stream=None) -> None`, `main(argv=None, ask=input) -> int` (0 done, 1 stopped by LinkedIn or Ctrl+C before anything was collected, 2 setup problem)

- [ ] **Step 1: Write the failing tests**

`tests/test_cli.py`:
```python
import io

from peerpatch_linkedin.cli import clamp_limits, make_console_safe, parse_args, resolve_search


def test_defaults():
    args = parse_args([])
    assert (args.job, args.location) == (None, None)
    assert (args.max_posts, args.max_jobs, args.post_hours, args.job_days) == (100, 200, 48, 7)
    assert not (args.skip_posts or args.skip_jobs or args.debug or args.no_open)


def test_job_flag_means_no_questions_and_india_by_default():
    asked = []
    assert resolve_search(parse_args(["--job", " data analyst "]), lambda q: asked.append(q) or "x") == ("data analyst", "India")
    assert asked == []


def test_asks_until_a_job_is_typed_then_defaults_location():
    answers = iter(["", "   ", "data analyst", ""])
    assert resolve_search(parse_args([]), lambda q: next(answers)) == ("data analyst", "India")


def test_typed_location_is_kept():
    answers = iter(["product manager", " Pune "])
    assert resolve_search(parse_args([]), lambda q: next(answers)) == ("product manager", "Pune")


def test_blank_location_flag_means_anywhere():
    assert resolve_search(parse_args(["--job", "x", "--location", ""]), input) == ("x", "")


def test_limits_are_clamped_with_a_message():
    args = parse_args(["--post-hours", "500", "--max-jobs", "0"])
    messages = []
    clamp_limits(args, messages.append)
    assert args.post_hours == 168 and args.max_jobs == 1
    assert "168" in messages[0]


def test_console_that_cannot_print_rupee_gets_question_marks():
    raw = io.BytesIO()
    stream = io.TextIOWrapper(raw, encoding="cp1252")
    make_console_safe(stream)
    stream.write("₹ 6,00,000 → done")
    stream.flush()
    assert raw.getvalue() == b"? 6,00,000 ? done"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_cli.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'peerpatch_linkedin.cli'`

- [ ] **Step 3: Write `cli.py` and `__main__.py`**

`peerpatch_linkedin/cli.py`:
```python
"""Read flags or ask questions, run the two searches, write the results."""
from __future__ import annotations

import argparse
import sys
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from . import config
from .browser import ChromeProblem, ScrapeResult, ScrapeStopped, ensure_logged_in, open_chrome
from .jobs import scrape_jobs
from .posts import scrape_posts
from .report import results_dir, write_results

MAX_POST_HOURS = 168


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="peerpatch_linkedin",
        description="Collect LinkedIn hiring posts (last 48 hours) and job listings (last 7 days) for a job title.",
    )
    parser.add_argument("--job", help='job title to search for, e.g. "data analyst"')
    parser.add_argument("--location", help="location for the jobs search (default: India; \"\" for anywhere)")
    parser.add_argument("--max-posts", type=int, default=100, help="stop after this many hiring posts (default 100)")
    parser.add_argument("--max-jobs", type=int, default=200, help="stop after this many jobs (default 200)")
    parser.add_argument("--post-hours", type=int, default=48, help="how far back posts go, 1 to 168 (default 48)")
    parser.add_argument("--job-days", type=int, default=7, help="how far back jobs go (default 7)")
    parser.add_argument("--skip-posts", action="store_true", help="only search jobs")
    parser.add_argument("--skip-jobs", action="store_true", help="only search posts")
    parser.add_argument("--debug", action="store_true", help="save the raw pages into the results folder")
    parser.add_argument("--no-open", action="store_true", help="don't open the report when done")
    parser.add_argument("--profile-dir", type=Path, default=config.TOOL_DIR / "chrome-profile",
                        help="where Chrome keeps the LinkedIn login (default: chrome-profile next to this tool)")
    parser.add_argument("--results-dir", type=Path, default=config.TOOL_DIR / "results",
                        help="where results go (default: results next to this tool)")
    return parser.parse_args(argv)


def resolve_search(args: argparse.Namespace, ask: Callable[[str], str]) -> tuple[str, str]:
    if args.job and args.job.strip():
        location = "India" if args.location is None else args.location
        return args.job.strip(), location.strip()
    job = ""
    while not job:
        job = ask("Job title: ").strip()
    if args.location is not None:
        return job, args.location.strip()
    return job, ask("Location (press Enter for India): ").strip() or "India"


def clamp_limits(args: argparse.Namespace, say: Callable[[str], None]) -> None:
    if not 1 <= args.post_hours <= MAX_POST_HOURS:
        fixed = min(max(args.post_hours, 1), MAX_POST_HOURS)
        say(f"--post-hours must be 1 to {MAX_POST_HOURS}. Using {fixed}.")
        args.post_hours = fixed
    args.job_days = max(1, args.job_days)
    args.max_posts = max(1, args.max_posts)
    args.max_jobs = max(1, args.max_jobs)


def make_console_safe(stream=None) -> None:
    """Old Windows consoles can't print every character. Print '?' instead of crashing."""
    for s in (sys.stdout, sys.stderr) if stream is None else (stream,):
        try:
            s.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass


def say(message: str) -> None:
    print(message, flush=True)


def main(argv: list[str] | None = None, ask: Callable[[str], str] = input) -> int:
    make_console_safe()
    args = parse_args(argv)
    clamp_limits(args, say)
    try:
        job, location = resolve_search(args, ask)
    except (EOFError, KeyboardInterrupt):
        say("\nNo job title given. Nothing to do.")
        return 2

    now = datetime.now(timezone.utc)
    out_dir = results_dir(args.results_dir, job, location, now.astimezone())
    debug_dir = out_dir / "debug" if args.debug else None
    posts, jobs, notes = ScrapeResult(), ScrapeResult(), []

    say(f"Searching LinkedIn for: {job} ({location or 'anywhere'})")
    try:
        with open_chrome(args.profile_dir) as page:
            ensure_logged_in(page, say)
            if not args.skip_posts:
                say(f"Hiring posts from the last {args.post_hours} hours...")
                posts = scrape_posts(page, job, say=say, max_hours=args.post_hours, max_posts=args.max_posts,
                                     debug_dir=debug_dir, now=now)
            if not args.skip_jobs and not posts.interrupted:
                say(f"Jobs from the last {args.job_days} days...")
                jobs = scrape_jobs(page, job, location, say=say, days=args.job_days, max_jobs=args.max_jobs,
                                   debug_dir=debug_dir)
    except ChromeProblem as problem:
        say(str(problem))
        return 2
    except ScrapeStopped as stop:
        say(str(stop))
        return 1
    except KeyboardInterrupt:
        if not (posts.items or jobs.items):
            say("\nStopped. Nothing was collected.")
            return 1
        notes.append("Stopped with Ctrl+C.")

    if posts.stopped:
        notes.append(f"Post search stopped early: {posts.stopped}")
    if jobs.stopped:
        notes.append(f"Jobs search stopped early: {jobs.stopped}")
    if args.skip_posts:
        notes.append("Post search was skipped.")
    if args.skip_jobs:
        notes.append("Jobs search was skipped.")
    elif posts.interrupted:
        notes.append("Jobs search didn't run because the run was stopped.")

    report = write_results(out_dir, job=job, location=location, run_at=now, post_hours=args.post_hours,
                           job_days=args.job_days, posts=posts.items, jobs=jobs.items, now=now, notes=notes)
    for note in notes:
        say(note)
    say(f"\nDone. {len(posts.items)} hiring posts, {len(jobs.items)} jobs.")
    say(f"Saved in: {out_dir}")
    if not args.no_open:
        webbrowser.open(report.resolve().as_uri())
    return 0
```

`peerpatch_linkedin/__main__.py`:
```python
from .cli import main

raise SystemExit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_cli.py -q && .venv/bin/python -m peerpatch_linkedin --help`
Expected: tests pass, help text prints

- [ ] **Step 5: Commit**

```bash
git add peerpatch_linkedin/cli.py peerpatch_linkedin/__main__.py tests/test_cli.py
git commit -m "Add command line and run flow"
```

---

### Task 9: End-to-end runs against a fake LinkedIn

**Files:**
- Create: `tests/fake_linkedin.py`, `tests/test_e2e.py`

**Interfaces:**
- Consumes: the whole package through `python -m peerpatch_linkedin`, and the markup builders from Task 4
- Produces: `FakeLinkedIn` with `.route(path, handler)`, `.start() -> base_url`, `.stop()`, `.requests: list[tuple[str, dict]]`. A handler takes the query dict and returns `(status, body, headers)`.

- [ ] **Step 1: Write the fake server**

`tests/fake_linkedin.py`:
```python
"""A tiny local stand-in for linkedin.com. Records every request."""
from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse


class FakeLinkedIn:
    def __init__(self):
        self.routes = {}
        self.requests = []
        self._server = None

    def route(self, path, handler):
        self.routes[path] = handler

    def start(self) -> str:
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                parsed = urlparse(self.path)
                query = {k: v[0] for k, v in parse_qs(parsed.query, keep_blank_values=True).items()}
                fake.requests.append((parsed.path, query))
                handler = fake.routes.get(parsed.path)
                status, body, headers = handler(query) if handler else (404, "not found", {})
                data = body.encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                for key, value in headers.items():
                    self.send_header(key, value)
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        return f"http://127.0.0.1:{self._server.server_port}"

    def stop(self):
        self._server.shutdown()
        self._server.server_close()
```

- [ ] **Step 2: Write the end-to-end tests**

`tests/test_e2e.py`:
```python
import csv
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from tests.fake_linkedin import FakeLinkedIn
from tests.linkedin_markup import (
    job_card, job_card_anchor, post_link_only, post_minimal, post_standard, search_page, urn_for,
)

ROOT = Path(__file__).resolve().parent.parent
OK = lambda body: (lambda q: (200, body, {}))  # noqa: E731
REDIRECT = lambda to: (lambda q: (302, "", {"Location": to}))  # noqa: E731
FEED = "<!doctype html><title>Feed | LinkedIn</title><main>feed</main>"


def build_posts_page():
    now = datetime.now(timezone.utc)

    def urn(hours, salt):
        return urn_for(now - timedelta(hours=hours), salt=salt)

    std = lambda h, s, who, text: post_standard(  # noqa: E731
        urn(h, s), who, "Recruiter", f"https://www.linkedin.com/in/{who.split()[0].lower()}", f"{int(h)}h", text, 10, 2)
    cards = [
        std(1, 1, "Priya Sharma", "We're hiring a Data Analyst in Bengaluru! DM me or send your CV."),
        post_minimal(urn(5, 2), "Acme Analytics", "https://www.linkedin.com/company/acme/",
                     "Openings for analysts in Pune. Apply now."),
        std(20, 3, "Rahul Verma", "Five SQL tricks every data analyst should know."),
        std(30, 4, "Neha Gupta", "I'm looking for a new role as a Data Analyst. #OpenToWork"),
        post_link_only(urn(40, 5), "Karan Mehta", "https://www.linkedin.com/in/karan",
                       "Hiring: Data Analyst intern, Gurugram. Referrals welcome."),
        std(47, 6, "Ananya Iyer", "My team is hiring 3 data analysts. Immediate joiners preferred."),
        std(50, 7, "Old Post", "Hiring data analysts."),
        std(60, 8, "Older Post", "Hiring data analysts."),
        std(80, 9, "Oldest Post", "Hiring data analysts."),
    ]
    return search_page(cards, batch=3)


def jobs_handler():
    calls = {"rate_limited": False}
    pages = {
        "0": [job_card(f"41000000{i:02d}", f"Data Analyst {i}", "Acme", "acme", "Bengaluru, Karnataka, India",
                       "2026-11-14", "1 day ago", salary="₹6,00,000.00 - ₹9,00,000.00" if i == 1 else "",
                       benefit="Actively Hiring" if i == 2 else "") for i in range(1, 11)],
        "10": [job_card_anchor(f"41000000{i:02d}", f"Data Analyst {i}", "Zeta", "Pune, Maharashtra, India",
                               "2026-11-12", "3 days ago") for i in range(11, 21)],
        "20": [job_card(f"41000000{i:02d}", f"Data Analyst {i}", "Acme", "acme", "Remote", "2026-11-09",
                        "6 days ago") for i in (21, 22, 23, 24, 5)],  # 41000000 05 repeats
    }

    def handler(query):
        start = query.get("start", "0")
        if start == "10" and not calls["rate_limited"]:
            calls["rate_limited"] = True
            return 429, "", {}
        return 200, "".join(pages.get(start, [])), {}

    return handler


def run_tool(base_url, tmp_path, *args, **env_overrides):
    env = dict(os.environ, PEERPATCH_LINKEDIN_BASE_URL=base_url, PEERPATCH_HEADLESS="1",
               PEERPATCH_WAIT_MIN="0.05", PEERPATCH_WAIT_MAX="0.1", PEERPATCH_RATE_LIMIT_PAUSE="0.2",
               **env_overrides)
    return subprocess.run(
        [sys.executable, "-m", "peerpatch_linkedin", "--job", "data analyst", "--location", "Bengaluru",
         "--profile-dir", str(tmp_path / "profile"), "--results-dir", str(tmp_path / "results"), "--no-open", *args],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=120,
    )


def read_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


@pytest.fixture
def fake():
    server = FakeLinkedIn()
    yield server
    server.stop()


def only_results_folder(tmp_path):
    folders = list((tmp_path / "results").iterdir())
    assert len(folders) == 1
    return folders[0]


def test_full_run(fake, tmp_path, browser):
    fake.route("/feed/", OK(FEED))
    fake.route("/search/results/content/", OK(build_posts_page()))
    fake.route("/jobs-guest/jobs/api/seeMoreJobPostings/search", jobs_handler())
    run = run_tool(fake.start(), tmp_path)
    assert run.returncode == 0, run.stdout + run.stderr

    out = only_results_folder(tmp_path)
    assert out.name.startswith("data-analyst_bengaluru_")
    posts = read_csv(out / "posts.csv")
    assert [p["author"] for p in posts] == ["Priya Sharma", "Acme Analytics", "Karan Mehta", "Ananya Iyer"]
    assert [p["mentions_title"] for p in posts] == ["yes", "no", "yes", "yes"]
    assert all(p["post_url"].startswith("https://www.linkedin.com/feed/update/urn:li:") for p in posts)

    jobs = read_csv(out / "jobs.csv")
    assert len(jobs) == 24
    assert jobs[0]["salary"] == "₹6,00,000.00 - ₹9,00,000.00"
    assert jobs[1]["benefit"] == "Actively Hiring"
    assert jobs[0]["job_url"] == "https://www.linkedin.com/jobs/view/4100000001/"

    job_requests = [q for path, q in fake.requests if path.startswith("/jobs-guest/")]
    assert [q["start"] for q in job_requests] == ["0", "10", "10", "20", "25"]
    assert all(q["f_TPR"] == "r604800" and q["sortBy"] == "DD" and q["keywords"] == "data analyst"
               and q["location"] == "Bengaluru" for q in job_requests)
    post_requests = [q for path, q in fake.requests if path == "/search/results/content/"]
    assert post_requests[0] == {"keywords": '"data analyst" hiring', "datePosted": '"past-week"',
                                "sortBy": '"date_posted"'}

    report = (out / "report.html").read_text(encoding="utf-8")
    assert "Hiring posts (4)" in report and "Jobs (24)" in report
    assert "slow down" in run.stdout


def test_no_login_in_time_saves_nothing(fake, tmp_path, browser):
    fake.route("/feed/", REDIRECT("/login"))
    fake.route("/login", OK("<!doctype html><title>Sign in</title>"))
    run = run_tool(fake.start(), tmp_path, PEERPATCH_LOGIN_TIMEOUT="1")
    assert run.returncode == 1
    assert "Log in to LinkedIn in the Chrome window" in run.stdout
    assert not (tmp_path / "results").exists()


def test_login_wall_on_posts_still_collects_jobs(fake, tmp_path, browser):
    fake.route("/feed/", OK(FEED))
    fake.route("/search/results/content/", REDIRECT("/authwall"))
    fake.route("/authwall", OK("<!doctype html><title>Sign in</title>"))
    fake.route("/jobs-guest/jobs/api/seeMoreJobPostings/search", jobs_handler())
    run = run_tool(fake.start(), tmp_path)
    assert run.returncode == 0, run.stdout + run.stderr

    out = only_results_folder(tmp_path)
    assert read_csv(out / "posts.csv") == []
    assert len(read_csv(out / "jobs.csv")) == 24
    assert "Post search stopped early: LinkedIn showed a login wall" in (out / "report.html").read_text(encoding="utf-8")


def test_skip_jobs_and_debug_pages(fake, tmp_path, browser):
    fake.route("/feed/", OK(FEED))
    fake.route("/search/results/content/", OK(build_posts_page()))
    run = run_tool(fake.start(), tmp_path, "--skip-jobs", "--debug")
    assert run.returncode == 0, run.stdout + run.stderr
    out = only_results_folder(tmp_path)
    assert (out / "debug" / "posts.html").exists()
    assert read_csv(out / "jobs.csv") == []
    assert not any(path.startswith("/jobs-guest/") for path, _ in fake.requests)
```

The `browser` fixture argument makes each test skip cleanly where Chrome isn't installed.

- [ ] **Step 3: Run the end-to-end tests**

Run: `.venv/bin/pytest tests/test_e2e.py -q`
Expected: 4 pass. If a run fails, the assertion message carries the tool's own output. Fix the package code, not the test, unless the test contradicts the spec.

- [ ] **Step 4: Run the whole suite**

Run: `.venv/bin/pytest -q`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add tests/fake_linkedin.py tests/test_e2e.py
git commit -m "Add end-to-end runs against a fake LinkedIn"
```

---

### Task 10: Launchers and README

**Files:**
- Create: `run.command`, `run.bat`, `README.md`

**Interfaces:**
- Consumes: `requirements.txt`, `python -m peerpatch_linkedin`
- Produces: nothing other code depends on

- [ ] **Step 1: Write `run.command`**

```bash
#!/bin/bash
# Mac: double-click this file. Mac or Linux terminal: bash run.command
cd "$(dirname "$0")" || exit 1

PY=""
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1 &&
     "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then
    PY="$candidate"
    break
  fi
done

if [ -z "$PY" ]; then
  echo "Python 3.9 or newer is needed. Get it from https://www.python.org/downloads/ and run this again."
  read -r -p "Press Enter to close."
  exit 1
fi

if [ ! -f .venv/.installed ]; then
  echo "First run: setting things up. This takes about a minute."
  rm -rf .venv
  if ! "$PY" -m venv .venv || ! .venv/bin/python -m pip install --quiet -r requirements.txt; then
    rm -rf .venv
    echo "Setup failed. Check your internet connection and run this again."
    read -r -p "Press Enter to close."
    exit 1
  fi
  touch .venv/.installed
fi

.venv/bin/python -m peerpatch_linkedin "$@"
status=$?
if [ $# -eq 0 ] && [ -t 0 ]; then
  read -r -p "Press Enter to close."
fi
exit $status
```

Then: `git update-index --add --chmod=+x run.command` after `git add`.

- [ ] **Step 2: Write `run.bat`** (saved with CRLF line endings through `.gitattributes`)

```bat
@echo off
setlocal
cd /d "%~dp0"

set "PY="
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>nul && set "PY=py -3"
if not defined PY python -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>nul && set "PY=python"
if not defined PY (
  echo Python 3.9 or newer is needed. Get it from https://www.python.org/downloads/
  echo When installing, tick "Add python.exe to PATH". Then run this again.
  pause
  exit /b 1
)

if not exist ".venv\.installed" (
  echo First run: setting things up. This takes about a minute.
  if exist ".venv" rmdir /s /q ".venv"
  %PY% -m venv .venv || goto setupfailed
  ".venv\Scripts\python.exe" -m pip install --quiet -r requirements.txt || goto setupfailed
  echo ok> ".venv\.installed"
)

".venv\Scripts\python.exe" -m peerpatch_linkedin %*
set "STATUS=%ERRORLEVEL%"
pause
exit /b %STATUS%

:setupfailed
if exist ".venv" rmdir /s /q ".venv"
echo Setup failed. Check your internet connection and run this again.
pause
exit /b 1
```

- [ ] **Step 3: Write `README.md`**

Plain language for someone who has never used a terminal. Sections, in this order:

1. **What it does**: one paragraph. Type a job title and a city, get LinkedIn hiring posts from the last 2 days and job listings from the last 7 days, saved as a spreadsheet and a web page.
2. **Before you start**: Google Chrome; Python 3.9+ from python.org (Windows: tick "Add python.exe to PATH"); a LinkedIn account.
3. **Get the tool**: on GitHub, Code, Download ZIP, unzip somewhere easy like Documents.
4. **Run it**: Windows, double-click `run.bat` (if SmartScreen warns, More info, Run anyway). Mac, right-click `run.command`, Open, Open (only the first time, because it isn't from the App Store). First run sets itself up for about a minute.
5. **First time only: log in**: a Chrome window opens. Log in to LinkedIn there. The login stays in the `chrome-profile` folder. The tool never sees your password. To log out for good, delete that folder.
6. **Answer two questions**: job title, location (Enter for India).
7. **What you get**: the `results` folder, one subfolder per search, with `posts.csv`, `jobs.csv` and `report.html` (opens on its own). One line on each CSV's columns.
8. **Options**: the flag table from the spec, with two terminal examples:
   - `bash run.command --job "data analyst" --location Pune`
   - `run.bat --job "product manager" --location "" --skip-posts`
9. **If something goes wrong**: "Google Chrome isn't installed"; "Another PeerPatch Chrome window is already open"; security check (solve it in the window, the tool waits 5 minutes); login wall or rate limit (results so far are saved, try again later); zero posts when there should be some (run with `--debug` and send the `debug` folder to whoever maintains this).
10. **Be careful with your account**: automated collection breaks LinkedIn's User Agreement. Accounts that do a lot of it can be restricted. Keep it to one search a day. You use this at your own risk.
11. **For developers**: `python3 -m venv .venv`, install both requirements files, `.venv/bin/pytest`. The test suite drives real Chrome against a fake LinkedIn, so it needs Chrome installed but no internet.

Write it in short sentences, no em dashes, straight quotes.

- [ ] **Step 4: Check the Mac/Linux launcher from a clean copy**

Run:
```bash
rm -rf /tmp/pp-launcher && git archive --format=tar HEAD | (mkdir -p /tmp/pp-launcher && tar -x -C /tmp/pp-launcher)
cp run.command run.bat README.md /tmp/pp-launcher/
bash /tmp/pp-launcher/run.command --help
```
Expected: "First run: setting things up", then the `--help` text. Run it a second time and the setup line doesn't appear. `run.bat` can't be run here; read it once more against the steps above.

- [ ] **Step 5: Commit**

```bash
git add run.command run.bat README.md
git update-index --chmod=+x run.command
git commit -m "Add double-click launchers and README"
```

---

### Task 11: Final check and push

- [ ] **Step 1:** Run `.venv/bin/pytest -q`. Expected: all pass.
- [ ] **Step 2:** `git status` is clean and `git ls-files` lists no `chrome-profile/`, `results/` or `.venv/`.
- [ ] **Step 3:** Push: `git -c push.negotiate=true push -u origin main`.
