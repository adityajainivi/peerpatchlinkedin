# Web Page and Any-Browser Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the terminal questions with a local web page (form, live progress, results, downloads), and let the tool drive Chrome, Edge, Brave or a downloaded built-in Chromium instead of Chrome only.

**Architecture:** `browsers.py` finds and picks a browser. `browser.py` launches it by path and gains a stop flag that `pause()` checks. The body of `cli.main` moves into `runner.run_search`, which both the terminal mode and the new `web.py` call. `web.py` is a standard-library HTTP server on 127.0.0.1 that runs one search at a time in a worker thread and serves `static/index.html`.

**Tech Stack:** Python 3.9+, Playwright for Python (sync API), `http.server`, vanilla HTML/CSS/JS, pytest.

**Spec:** `docs/superpowers/specs/2026-11-15-web-ui-and-browsers-design.md` (builds on `docs/superpowers/specs/2026-11-15-linkedin-scraper-design.md`)

## Global Constraints

- Python 3.9 or newer; every module starts with `from __future__ import annotations`.
- No new runtime dependencies. The server is `http.server.ThreadingHTTPServer`.
- Browser order: chrome, edge, brave; if none is installed, builtin. chrome, edge and brave are launched with `executable_path=<found path>`; builtin is launched with no path.
- Login folders: `<profile_base>/browser-profiles/<key>/`. An existing `<profile_base>/chrome-profile/` moves to `browser-profiles/chrome/` if that doesn't exist yet.
- Builtin download command: `python -m playwright install chromium`. Failure message: "Couldn't download the built-in browser. Check your internet connection, or install Chrome or Edge."
- Server address: `127.0.0.1` only. Port 8765, then the next free port up to 8784, then any free port.
- Token: `secrets.token_urlsafe(16)`, sent as header `X-PeerPatch-Token` or query `?t=`. Missing or wrong token: 403. `Host` must be `127.0.0.1:<port>` or `localhost:<port>`, else 403.
- One run at a time, in one worker thread. `POST /api/start` returns 409 while a run is going.
- Stop: `request_stop()` sets a flag. `pause()` checks it every 0.2 seconds and raises `Cancelled`. The scrapers treat `Cancelled` like Ctrl+C.
- Stage names: `starting`, `downloading-browser`, `waiting-for-login`, `posts`, `jobs`, `saving`, `done`.
- Messages that named Chrome now use the browser's label ("Chrome", "Edge", "Brave", "Built-in browser").
- No `--job`: start the web page. `--job`: run in the terminal. New flags: `--browser {auto,chrome,edge,brave,builtin}` (default auto) and `--port` (default 8765).
- Everything from the first spec stays: stop the whole run when LinkedIn pushes back, save partial results, the same CSV and report formats.
- The page loads nothing from the internet, and all dynamic text goes in with `textContent`.
- Console messages are plain ASCII.
- Test HTTP clients bypass the machine's proxy (`urllib.request.ProxyHandler({})`), because this build container has `HTTP_PROXY` set.

## Review Focus

1. Reopening the page link while a search is running should show that search's progress, not an empty form. Pinned in Task 5 (`test_reopening_the_link_during_a_run_shows_its_progress`).
2. Closing the terminal while the page is open: the next click should say PeerPatch has stopped, not hang or do nothing. Pinned in Task 5 (`test_closing_peerpatch_shows_that_it_stopped`).
3. A second launch while the first is still running should get its own port, not steal or fail. On Windows, `SO_REUSEADDR` lets two servers share a port, so it's turned off there. Pinned in Task 4 (`test_busy_port_moves_to_the_next_one`).
4. Pressing Stop while the tool waits for login should end cleanly with nothing saved. Pinned in Task 2 (`test_stop_during_login_wait_cancels`) and Task 6 (`test_stop_while_waiting_for_login_saves_nothing`).
5. A job title containing HTML should show as text, not markup. Pinned in Task 5 (`test_job_title_with_markup_is_shown_as_text`).

---

## File map

```
peerpatch_linkedin/
  browsers.py        NEW   find, pick, download the browser; login folder per browser
  browser.py         EDIT  open_browser(info, profile_dir), BrowserProblem, labels, stop flag, Cancelled, on_wait
  posts.py, jobs.py  EDIT  catch Cancelled
  runner.py          NEW   SearchOptions, RunOutcome, validate, run_search
  web.py             NEW   RunState, App, parse_start, list_runs, make_server, serve
  static/index.html  NEW   the page
  cli.py             EDIT  terminal mode through runner; no --job means web mode
tests/
  fake_page.py       NEW   a fake Playwright page for stop tests
  web_client.py      NEW   start the server in a thread, call it, fake run function
  test_browsers.py, test_stop.py, test_runner.py, test_web.py, test_page.py, test_live_flow.py   NEW
  test_browser.py, test_cli.py   EDIT
README.md            EDIT
```

All commands run from the repo root with the existing `.venv`.

---

### Task 1: Find and pick a browser (`browsers.py`)

**Files:**
- Create: `peerpatch_linkedin/browsers.py`
- Test: `tests/test_browsers.py`

**Interfaces:**
- Produces:
  - `ORDER = ("chrome", "edge", "brave")`, `LABELS: dict[str, str]`, `KEYS = ("auto", "chrome", "edge", "brave", "builtin")`
  - `class BrowserNotFound(Exception)`, `class BrowserDownloadFailed(Exception)`
  - `@dataclass(frozen=True) BrowserInfo(key: str, label: str, path: str | None, installed: bool)`
  - `candidate_paths(key, platform, env, home) -> list[str]`
  - `builtin_executable_path() -> str` (cached; "" if Playwright can't say)
  - `find_browsers(*, platform=None, env=None, home=None, exists=os.path.exists, builtin_path=None) -> list[BrowserInfo]` (installed chrome/edge/brave in order, then builtin, always last)
  - `default_browser(browsers) -> BrowserInfo`
  - `choose_browser(key: str, browsers) -> BrowserInfo` (raises `BrowserNotFound`)
  - `launch_options(info) -> dict`
  - `install_builtin(say, command=None) -> None` (raises `BrowserDownloadFailed`)
  - `profile_dir_for(base: Path, key: str) -> Path`

- [ ] **Step 1: Write the failing tests**

`tests/test_browsers.py`:
```python
import sys

import pytest

from peerpatch_linkedin.browsers import (
    BrowserDownloadFailed, BrowserInfo, BrowserNotFound, candidate_paths, choose_browser, default_browser,
    find_browsers, install_builtin, launch_options, profile_dir_for,
)

WIN_ENV = {"PROGRAMFILES": r"C:\Program Files", "PROGRAMFILES(X86)": r"C:\Program Files (x86)",
           "LOCALAPPDATA": r"C:\Users\asha\AppData\Local"}


def only(*paths):
    present = set(paths)
    return lambda path: path in present


def summary(browsers):
    return [(b.key, b.installed) for b in browsers]


def test_windows_with_only_edge_defaults_to_edge():
    edge = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
    browsers = find_browsers(platform="win32", env=WIN_ENV, home="", exists=only(edge), builtin_path="/nope")
    assert summary(browsers) == [("edge", True), ("builtin", False)]
    assert default_browser(browsers).key == "edge"
    assert launch_options(browsers[0]) == {"executable_path": edge}


def test_mac_prefers_chrome_and_finds_it_under_home_applications():
    chrome = "/Users/asha/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    brave = "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"
    browsers = find_browsers(platform="darwin", env={}, home="/Users/asha", exists=only(chrome, brave),
                             builtin_path="/nope")
    assert summary(browsers) == [("chrome", True), ("brave", True), ("builtin", False)]
    assert default_browser(browsers).path == chrome


def test_linux_with_only_brave():
    browsers = find_browsers(platform="linux", env={}, home="/home/a", exists=only("/usr/bin/brave-browser"),
                             builtin_path="/nope")
    assert default_browser(browsers).key == "brave"


def test_nothing_installed_falls_back_to_the_builtin_browser():
    browsers = find_browsers(platform="darwin", env={}, home="/Users/a", exists=only("/pw/chrome"),
                             builtin_path="/pw/chrome")
    assert summary(browsers) == [("builtin", True)]
    assert default_browser(browsers).key == "builtin"
    assert launch_options(browsers[0]) == {}


def test_windows_paths_skip_missing_environment_variables():
    assert candidate_paths("chrome", "win32", {"LOCALAPPDATA": r"C:\L"}, "") == [
        r"C:\L\Google\Chrome\Application\chrome.exe"]


def test_choose_browser():
    browsers = [BrowserInfo("edge", "Edge", "e.exe", True), BrowserInfo("builtin", "Built-in browser", None, False)]
    assert choose_browser("auto", browsers).key == "edge"
    assert choose_browser("BUILTIN", browsers).key == "builtin"
    with pytest.raises(BrowserNotFound, match="Chrome isn't installed on this computer"):
        choose_browser("chrome", browsers)
    with pytest.raises(BrowserNotFound, match="Unknown browser"):
        choose_browser("safari", browsers)


def test_old_chrome_login_folder_moves_once(tmp_path):
    (tmp_path / "chrome-profile" / "Default").mkdir(parents=True)
    target = profile_dir_for(tmp_path, "chrome")
    assert target == tmp_path / "browser-profiles" / "chrome"
    assert (target / "Default").is_dir()
    assert not (tmp_path / "chrome-profile").exists()
    assert profile_dir_for(tmp_path, "edge") == tmp_path / "browser-profiles" / "edge"


def test_old_login_folder_is_left_alone_when_the_new_one_exists(tmp_path):
    (tmp_path / "chrome-profile").mkdir()
    (tmp_path / "browser-profiles" / "chrome").mkdir(parents=True)
    profile_dir_for(tmp_path, "chrome")
    assert (tmp_path / "chrome-profile").exists()


def test_install_builtin_streams_output_and_reports_failure():
    lines = []
    install_builtin(lines.append, command=[sys.executable, "-c", "print('Downloading Chromium'); print('50%\\r100%')"])
    assert lines == ["  Downloading Chromium", "  50%", "  100%"]
    with pytest.raises(BrowserDownloadFailed, match="Check your internet connection"):
        install_builtin(lines.append, command=[sys.executable, "-c", "import sys; sys.exit(3)"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_browsers.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'peerpatch_linkedin.browsers'`

- [ ] **Step 3: Write `browsers.py`**

```python
"""Find a browser to drive: Chrome, then Edge, then Brave, else Playwright's own Chromium."""
from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Callable, Mapping

ORDER = ("chrome", "edge", "brave")
LABELS = {"chrome": "Chrome", "edge": "Edge", "brave": "Brave", "builtin": "Built-in browser"}
KEYS = ("auto",) + ORDER + ("builtin",)

_DOWNLOAD_FAILED = "Couldn't download the built-in browser. Check your internet connection, or install Chrome or Edge."

_MAC_APPS = {
    "chrome": "Google Chrome.app/Contents/MacOS/Google Chrome",
    "edge": "Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "brave": "Brave Browser.app/Contents/MacOS/Brave Browser",
}
_WINDOWS = {
    "chrome": (("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"), r"Google\Chrome\Application\chrome.exe"),
    "edge": (("PROGRAMFILES(X86)", "PROGRAMFILES"), r"Microsoft\Edge\Application\msedge.exe"),
    "brave": (("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"), r"BraveSoftware\Brave-Browser\Application\brave.exe"),
}
_LINUX = {
    "chrome": ("/opt/google/chrome/chrome",),
    "edge": ("/opt/microsoft/msedge/msedge",),
    "brave": ("/opt/brave.com/brave/brave", "/usr/bin/brave-browser"),
}


class BrowserNotFound(Exception):
    """The browser someone asked for isn't on this computer."""


class BrowserDownloadFailed(Exception):
    """The built-in browser couldn't be downloaded."""


@dataclass(frozen=True)
class BrowserInfo:
    key: str
    label: str
    path: str | None
    installed: bool


def candidate_paths(key: str, platform: str, env: Mapping[str, str], home: str) -> list[str]:
    if platform == "darwin":
        app = _MAC_APPS[key]
        return [f"/Applications/{app}", f"{home}/Applications/{app}"]
    if platform.startswith("win"):
        names, tail = _WINDOWS[key]
        return [f"{env[name]}\\{tail}" for name in names if env.get(name)]
    return list(_LINUX[key])


@lru_cache(maxsize=1)
def builtin_executable_path() -> str:
    """Where Playwright keeps its own Chromium, or "" if Playwright can't say. Looked up once."""
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            return playwright.chromium.executable_path
    except Exception:
        return ""


def find_browsers(*, platform: str | None = None, env: Mapping[str, str] | None = None, home: str | None = None,
                  exists: Callable[[str], bool] = os.path.exists, builtin_path: str | None = None) -> list[BrowserInfo]:
    """Installed Chrome, Edge and Brave in that order, then the built-in browser, which is always listed."""
    platform = sys.platform if platform is None else platform
    env = os.environ if env is None else env
    home = str(Path.home()) if home is None else home
    found = []
    for key in ORDER:
        path = next((p for p in candidate_paths(key, platform, env, home) if exists(p)), None)
        if path:
            found.append(BrowserInfo(key, LABELS[key], path, True))
    builtin_path = builtin_executable_path() if builtin_path is None else builtin_path
    found.append(BrowserInfo("builtin", LABELS["builtin"], None, bool(builtin_path) and exists(builtin_path)))
    return found


def default_browser(browsers: list[BrowserInfo]) -> BrowserInfo:
    return next((b for b in browsers if b.key in ORDER), browsers[-1])


def choose_browser(key: str, browsers: list[BrowserInfo]) -> BrowserInfo:
    key = (key or "auto").lower()
    if key == "auto":
        return default_browser(browsers)
    if key not in LABELS:
        raise BrowserNotFound(f"Unknown browser '{key}'. Pick one of: chrome, edge, brave, builtin.")
    for browser in browsers:
        if browser.key == key:
            return browser
    raise BrowserNotFound(f"{LABELS[key]} isn't installed on this computer. Pick another browser.")


def launch_options(info: BrowserInfo) -> dict:
    return {"executable_path": info.path} if info.path else {}


def install_builtin(say: Callable[[str], None], command: list[str] | None = None) -> None:
    """Download Playwright's Chromium, passing its progress lines to `say`."""
    command = command or [sys.executable, "-m", "playwright", "install", "chromium"]
    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                   errors="replace")
    except OSError:
        raise BrowserDownloadFailed(_DOWNLOAD_FAILED) from None
    for line in process.stdout:  # text mode splits on \r too, so progress updates arrive as lines
        line = line.strip()
        if line:
            say(f"  {line}")
    if process.wait() != 0:
        raise BrowserDownloadFailed(_DOWNLOAD_FAILED)


def profile_dir_for(base: Path, key: str) -> Path:
    """Each browser keeps its own LinkedIn login. The old single chrome-profile folder moves over once."""
    target = base / "browser-profiles" / key
    old = base / "chrome-profile"
    if key == "chrome" and old.is_dir() and not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        old.rename(target)
    return target
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_browsers.py -q`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add peerpatch_linkedin/browsers.py tests/test_browsers.py
git commit -m "Add browser detection: Chrome, Edge, Brave or a built-in Chromium"
```

---

### Task 2: Launch any browser, and stop on request (`browser.py`, `posts.py`, `jobs.py`)

**Files:**
- Modify: `peerpatch_linkedin/browser.py` (whole file shown below)
- Modify: `peerpatch_linkedin/posts.py`, `peerpatch_linkedin/jobs.py` (import and except blocks)
- Modify: `peerpatch_linkedin/cli.py` (three lines, so the suite stays green until Task 3 replaces `main`)
- Create: `tests/fake_page.py`, `tests/test_stop.py`
- Modify: `tests/test_browser.py` (two tests)

**Interfaces:**
- Consumes: `browsers.BrowserInfo`, `browsers.launch_options` (Task 1)
- Produces (in `browser.py`):
  - `class BrowserProblem(Exception)` (replaces `ChromeProblem`), `class Cancelled(Exception)`
  - `request_stop()`, `clear_stop()`, `stop_requested() -> bool`
  - `explain_launch_error(message, profile_dir, label="Chrome") -> str`
  - `open_browser(info: BrowserInfo, profile_dir: Path)` context manager yielding a page (replaces `open_chrome`)
  - `pause(page, seconds)` now raises `Cancelled` when a stop was requested
  - `ensure_logged_in(page, say, *, label="Chrome", on_wait=None, timeout=None, poll=2.0)`
  - unchanged: `ScrapeStopped`, `ScrapeResult`, `Say`, `first_line`, `classify_url`, `open_url`, `polite_wait`, `is_logged_in`, `check_for_walls`, `run_extract`, `save_debug`
- Produces (tests): `tests.fake_page.FakePage(url=..., goto_url=None, jobs=None)`

- [ ] **Step 1: Write the failing tests**

`tests/fake_page.py`:
```python
"""Just enough of a Playwright page to test waiting and stopping without a browser."""
from types import SimpleNamespace


class FakePage:
    def __init__(self, url="http://127.0.0.1/feed/", goto_url=None, jobs=None):
        self.url = url
        self.goto_url = goto_url  # where goto() lands; None means the URL asked for
        self.jobs = jobs or []
        self.waits = []
        self.context = SimpleNamespace(cookies=lambda: [])

    def goto(self, url, wait_until=None):
        self.url = self.goto_url or url
        return SimpleNamespace(status=200)

    def wait_for_timeout(self, ms):
        self.waits.append(ms)

    def on(self, event, handler):
        pass

    def remove_listener(self, event, handler):
        pass

    def evaluate(self, script):
        return list(self.jobs)

    def content(self):
        return ""
```

`tests/test_stop.py`:
```python
import pytest

from peerpatch_linkedin.browser import Cancelled, clear_stop, ensure_logged_in, pause, request_stop
from peerpatch_linkedin.jobs import scrape_jobs
from peerpatch_linkedin.posts import scrape_posts
from tests.fake_page import FakePage


@pytest.fixture(autouse=True)
def no_leftover_stop():
    clear_stop()
    yield
    clear_stop()


def test_pause_waits_in_small_steps():
    page = FakePage()
    pause(page, 0.5)
    assert sum(page.waits) == pytest.approx(500)
    assert max(page.waits) <= 200


def test_stop_request_cancels_a_pause_before_it_waits():
    page = FakePage()
    request_stop()
    with pytest.raises(Cancelled):
        pause(page, 5)
    assert page.waits == []


def test_stop_during_login_wait_cancels():
    page = FakePage(goto_url="http://127.0.0.1/login")
    said = []

    def on_wait():
        said.append("<waiting>")
        request_stop()

    with pytest.raises(Cancelled):
        ensure_logged_in(page, said.append, label="Edge", on_wait=on_wait, timeout=60)
    assert said[0] == "Log in to LinkedIn in the Edge window, then come back here."
    assert said[-1] == "<waiting>"


def test_stop_ends_the_post_search_as_interrupted():
    request_stop()
    result = scrape_posts(FakePage(), "data analyst", say=lambda m: None)
    assert (result.items, result.stopped, result.interrupted) == ([], "Stopped from the page.", True)


def test_stop_ends_the_jobs_search_keeping_jobs_found():
    page = FakePage(jobs=[{"job_id": "4100000001", "title": "Data Analyst"}])
    request_stop()
    result = scrape_jobs(page, "data analyst", "India", say=lambda m: None)
    assert [j.job_id for j in result.items] == ["4100000001"]
    assert (result.stopped, result.interrupted) == ("Stopped from the page.", True)
```

In `tests/test_browser.py`, replace `test_missing_chrome_is_explained` and `test_profile_in_use_is_explained` with:
```python
def test_missing_browser_is_explained(tmp_path):
    msg = explain_launch_error("Chromium distribution 'chrome' is not found at /x", tmp_path, "Edge")
    assert msg == "Edge couldn't be found on this computer. Pick another browser and try again."


def test_profile_in_use_is_explained(tmp_path):
    os.symlink("somehost-1234", tmp_path / "SingletonLock")  # dangling, the way Chrome leaves it
    msg = explain_launch_error("Target page, context or browser has been closed", tmp_path, "Brave")
    assert msg == "Another PeerPatch Brave window is already open. Close it and run this again."
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_stop.py tests/test_browser.py -q`
Expected: `test_stop.py` fails to import (`cannot import name 'Cancelled'`). After `--ignore=tests/test_stop.py`, the two `test_browser.py` tests fail on the old wording.

- [ ] **Step 3: Replace `peerpatch_linkedin/browser.py`**

```python
"""Everything that touches the browser: launch, login, walls, waits, stopping and in-page scripts."""
from __future__ import annotations

import os
import random
import threading
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
from .browsers import BrowserInfo, launch_options

Say = Callable[[str], None]
_stop = threading.Event()


class ScrapeStopped(Exception):
    """LinkedIn put up a wall we can't get past. The message says which."""


class BrowserProblem(Exception):
    """The browser wouldn't start. The message tells the person what to do."""


class Cancelled(Exception):
    """The person pressed Stop on the web page."""


@dataclass
class ScrapeResult:
    items: list = field(default_factory=list)
    stopped: str | None = None
    interrupted: bool = False
    blocked: bool = False  # LinkedIn pushed back (login wall, unsolved check, closed window): don't keep going


def request_stop() -> None:
    _stop.set()


def clear_stop() -> None:
    _stop.clear()


def stop_requested() -> bool:
    return _stop.is_set()


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


def explain_launch_error(message: str, profile_dir: Path, label: str = "Chrome") -> str:
    text = message.lower()
    if "is not found" in text or "executable doesn't exist" in text:
        return f"{label} couldn't be found on this computer. Pick another browser and try again."
    if any(os.path.lexists(profile_dir / name) for name in ("SingletonLock", "lockfile")):
        return f"Another PeerPatch {label} window is already open. Close it and run this again."
    return f"{label} wouldn't start: {first_line(Exception(message))}"


@contextmanager
def open_browser(info: BrowserInfo, profile_dir: Path) -> Iterator:
    profile_dir.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        try:
            context = playwright.chromium.launch_persistent_context(
                str(profile_dir),
                headless=config.HEADLESS,
                no_viewport=not config.HEADLESS,
                **launch_options(info),
            )
        except PlaywrightError as err:
            raise BrowserProblem(explain_launch_error(str(err), profile_dir, info.label)) from None
        try:
            yield context.pages[0] if context.pages else context.new_page()
        finally:
            try:
                context.close()
            except Exception:
                pass


def open_url(page, url: str) -> int:
    """Go to a URL and return the HTTP status.

    When a server answers an error code with an empty body, Chrome shows its own error page and
    Playwright raises instead of returning the response. The status is read from the response event.
    """
    statuses: list[int] = []

    def on_response(response) -> None:
        if response.request.is_navigation_request() and response.frame == page.main_frame:
            statuses.append(response.status)

    page.on("response", on_response)
    try:
        response = page.goto(url, wait_until="domcontentloaded")
        return response.status if response else (statuses[-1] if statuses else 200)
    except PlaywrightError:
        if statuses:
            return statuses[-1]
        raise
    finally:
        page.remove_listener("response", on_response)


def pause(page, seconds: float) -> None:
    """Wait, in steps of 0.2 seconds so Stop takes effect quickly."""
    remaining = max(0.0, seconds)
    while True:
        if _stop.is_set():
            raise Cancelled()
        if remaining <= 0:
            return
        step = min(0.2, remaining)
        try:
            page.wait_for_timeout(step * 1000)
        except PlaywrightError:
            raise ScrapeStopped("The browser window was closed.") from None
        remaining -= step


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


def ensure_logged_in(page, say: Say, *, label: str = "Chrome", on_wait: Callable[[], None] | None = None,
                     timeout: float | None = None, poll: float = 2.0) -> None:
    timeout = config.LOGIN_TIMEOUT_SECONDS if timeout is None else timeout
    try:
        page.goto(f"{config.BASE_URL}/feed/", wait_until="domcontentloaded")
    except PlaywrightError as err:
        raise ScrapeStopped(f"Couldn't open LinkedIn: {first_line(err)}") from None
    if is_logged_in(page):
        return
    say(f"Log in to LinkedIn in the {label} window, then come back here.")
    say("Use your LinkedIn email and password. This window doesn't have your saved passwords, and")
    say("'Continue with Google' or Apple may be blocked in it. Ignore the 'controlled by automated")
    say("test software' bar at the top; that's this tool.")
    say(f"Waiting up to {_minutes(timeout)} minutes...")
    if on_wait:
        on_wait()
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
    say(f"LinkedIn wants a security check. Solve it in the browser window. Waiting up to {_minutes(timeout)} minutes...")
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

- [ ] **Step 4: Catch `Cancelled` in the scrapers**

In `peerpatch_linkedin/posts.py`, change the `from .browser import (...)` block to:
```python
from .browser import (
    Cancelled, ScrapeResult, ScrapeStopped, Say, check_for_walls, first_line, polite_wait, run_extract, save_debug,
)
```
and the end of `scrape_posts` to:
```python
    except ScrapeStopped as stop:
        save_debug(page, debug_dir, "posts-stopped")
        return result(str(stop), blocked=True)
    except PlaywrightError as err:
        return result(f"The browser had a problem during the post search: {first_line(err)}")
    except Cancelled:
        return result("Stopped from the page.", interrupted=True)
    except KeyboardInterrupt:
        return result("Stopped with Ctrl+C.", interrupted=True)
    return result()
```

In `peerpatch_linkedin/jobs.py`, change the import block to:
```python
from .browser import (
    Cancelled, ScrapeResult, ScrapeStopped, Say, check_for_walls, first_line, open_url, pause, polite_wait,
    run_extract, save_debug,
)
```
and the end of `scrape_jobs` to:
```python
    except ScrapeStopped as stop:
        return result(str(stop))
    except PlaywrightError as err:
        return result(f"The browser had a problem during the jobs search: {first_line(err)}")
    except Cancelled:
        return result("Stopped from the page.", interrupted=True)
    except KeyboardInterrupt:
        return result("Stopped with Ctrl+C.", interrupted=True)
    return result()
```

- [ ] **Step 5: Keep `cli.py` working on the new names**

In `peerpatch_linkedin/cli.py`:
- replace `from .browser import ChromeProblem, ScrapeResult, ScrapeStopped, ensure_logged_in, open_chrome` with
  ```python
  from .browser import BrowserProblem, ScrapeResult, ScrapeStopped, ensure_logged_in, open_browser
  from .browsers import choose_browser, find_browsers, profile_dir_for
  ```
- replace
  ```python
          with open_chrome(args.profile_dir) as page:
              ensure_logged_in(page, say)
  ```
  with
  ```python
          info = choose_browser("auto", find_browsers())
          with open_browser(info, profile_dir_for(args.profile_dir, info.key)) as page:
              ensure_logged_in(page, say, label=info.label)
  ```
- replace `except ChromeProblem as problem:` with `except BrowserProblem as problem:`.

- [ ] **Step 6: Run the whole suite**

Run: `.venv/bin/pytest -q`
Expected: all pass, including the end-to-end runs in `tests/test_e2e.py`, which now find Chrome at `/opt/google/chrome/chrome` and launch it by path.

- [ ] **Step 7: Commit**

```bash
git add peerpatch_linkedin/browser.py peerpatch_linkedin/posts.py peerpatch_linkedin/jobs.py peerpatch_linkedin/cli.py tests/fake_page.py tests/test_stop.py tests/test_browser.py
git commit -m "Launch any detected browser by path; add a stop flag the waits respect"
```

---

### Task 3: Shared run logic (`runner.py`) and the terminal mode on top of it

**Files:**
- Create: `peerpatch_linkedin/runner.py`
- Modify: `peerpatch_linkedin/cli.py`
- Create: `tests/test_runner.py`
- Modify: `tests/test_cli.py`

**Interfaces:**
- Consumes: Task 1 (`choose_browser`, `find_browsers`, `install_builtin`, `profile_dir_for`, `BrowserInfo`, `BrowserNotFound`, `BrowserDownloadFailed`), Task 2 (`open_browser`, `ensure_logged_in`, `clear_stop`, `Cancelled`, `BrowserProblem`, `ScrapeStopped`, `ScrapeResult`, `first_line`), `scrape_posts`, `scrape_jobs`, `results_dir`, `write_results`
- Produces:
  - `MAX_POST_HOURS = 168`
  - `@dataclass SearchOptions(job, location="India", browser="auto", max_posts=100, max_jobs=200, post_hours=48, job_days=7, skip_posts=False, skip_jobs=False, debug=False, profile_base=TOOL_DIR, results_dir=TOOL_DIR/"results")`
  - `@dataclass RunOutcome(out_dir: Path | None, posts: list, jobs: list, notes: list, error: str | None, exit_code: int)` with `.report -> Path | None`
  - `validate(options) -> str | None`
  - `run_search(options, say, stage=lambda name: None, browsers=None) -> RunOutcome`
  - in `cli.py`: `options_from_args(args, job, location) -> SearchOptions`, `report_outcome(outcome, open_report: bool) -> int`, new flags `--browser`, `--port`

- [ ] **Step 1: Write the failing tests**

`tests/test_runner.py`:
```python
from peerpatch_linkedin.browsers import BrowserInfo
from peerpatch_linkedin.runner import SearchOptions, run_search, validate


def test_validate():
    assert validate(SearchOptions(job="  ")) == "Type a job title."
    assert validate(SearchOptions(job="x", post_hours=169)) == "Post hours must be 1 to 168."
    assert validate(SearchOptions(job="x", job_days=0)) == "Job days must be at least 1."
    assert validate(SearchOptions(job="x", max_jobs=0)) == "Max posts and max jobs must be at least 1."
    assert validate(SearchOptions(job="x")) is None


def test_invalid_options_never_open_a_browser(tmp_path):
    outcome = run_search(SearchOptions(job="", results_dir=tmp_path), say=lambda m: None)
    assert (outcome.out_dir, outcome.exit_code, outcome.error) == (None, 2, "Type a job title.")


def test_a_missing_browser_is_a_setup_problem(tmp_path):
    stages = []
    outcome = run_search(
        SearchOptions(job="x", browser="chrome", results_dir=tmp_path / "results", profile_base=tmp_path),
        say=lambda m: None, stage=stages.append,
        browsers=[BrowserInfo("builtin", "Built-in browser", None, True)],
    )
    assert (outcome.out_dir, outcome.exit_code) == (None, 2)
    assert outcome.error == "Chrome isn't installed on this computer. Pick another browser."
    assert stages == ["starting"]
    assert list(tmp_path.iterdir()) == []
```

Append to `tests/test_cli.py`:
```python
def test_browser_and_port_flags():
    args = parse_args([])
    assert (args.browser, args.port) == ("auto", 8765)
    args = parse_args(["--browser", "edge", "--port", "9000"])
    assert (args.browser, args.port) == ("edge", 9000)


def test_options_from_args_carries_every_setting(tmp_path):
    from peerpatch_linkedin.cli import options_from_args

    args = parse_args(["--job", "x", "--browser", "brave", "--max-posts", "5", "--skip-jobs",
                       "--profile-dir", str(tmp_path), "--results-dir", str(tmp_path / "r")])
    options = options_from_args(args, "x", "Pune")
    assert (options.job, options.location, options.browser, options.max_posts, options.skip_jobs) == (
        "x", "Pune", "brave", 5, True)
    assert (options.profile_base, options.results_dir) == (tmp_path, tmp_path / "r")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_runner.py tests/test_cli.py -q`
Expected: `test_runner.py` fails to import (`No module named 'peerpatch_linkedin.runner'`). After `--ignore=tests/test_runner.py`, the two new CLI tests fail (`unrecognized arguments: --browser`).

- [ ] **Step 3: Write `runner.py`**

```python
"""Run one search from start to finish. The terminal mode and the web page both use this."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from . import config
from .browser import (
    BrowserProblem, Cancelled, ScrapeResult, ScrapeStopped, Say, clear_stop, ensure_logged_in, first_line,
    open_browser,
)
from .browsers import (
    BrowserDownloadFailed, BrowserInfo, BrowserNotFound, choose_browser, find_browsers, install_builtin,
    profile_dir_for,
)
from .jobs import scrape_jobs
from .posts import scrape_posts
from .report import results_dir, write_results

MAX_POST_HOURS = 168
Stage = Callable[[str], None]


@dataclass
class SearchOptions:
    job: str
    location: str = "India"
    browser: str = "auto"
    max_posts: int = 100
    max_jobs: int = 200
    post_hours: int = 48
    job_days: int = 7
    skip_posts: bool = False
    skip_jobs: bool = False
    debug: bool = False
    profile_base: Path = field(default_factory=lambda: config.TOOL_DIR)
    results_dir: Path = field(default_factory=lambda: config.TOOL_DIR / "results")


@dataclass
class RunOutcome:
    out_dir: Path | None
    posts: list
    jobs: list
    notes: list
    error: str | None
    exit_code: int

    @property
    def report(self) -> Path | None:
        return self.out_dir / "report.html" if self.out_dir else None


def validate(options: SearchOptions) -> str | None:
    if not options.job.strip():
        return "Type a job title."
    if not 1 <= options.post_hours <= MAX_POST_HOURS:
        return f"Post hours must be 1 to {MAX_POST_HOURS}."
    if options.job_days < 1:
        return "Job days must be at least 1."
    if options.max_posts < 1 or options.max_jobs < 1:
        return "Max posts and max jobs must be at least 1."
    return None


def _failed(error: str, exit_code: int) -> RunOutcome:
    return RunOutcome(None, [], [], [], error, exit_code)


def run_search(options: SearchOptions, say: Say, stage: Stage = lambda name: None,
               browsers: list[BrowserInfo] | None = None) -> RunOutcome:
    problem = validate(options)
    if problem:
        return _failed(problem, 2)
    clear_stop()
    stage("starting")
    job, location = options.job.strip(), options.location.strip()
    now = datetime.now(timezone.utc)
    out_dir = results_dir(options.results_dir, job, location, now.astimezone())
    debug_dir = out_dir / "debug" if options.debug else None
    posts, jobs, notes = ScrapeResult(), ScrapeResult(), []
    error = None
    try:
        info = choose_browser(options.browser, find_browsers() if browsers is None else browsers)
        if info.key == "builtin" and not info.installed:
            stage("downloading-browser")
            say("Downloading the built-in browser. This happens once and can take a few minutes...")
            install_builtin(say)
        say(f"Searching LinkedIn for: {job} ({location or 'anywhere'}), using {info.label}")
        with open_browser(info, profile_dir_for(options.profile_base, info.key)) as page:
            ensure_logged_in(page, say, label=info.label, on_wait=lambda: stage("waiting-for-login"))
            if not options.skip_posts:
                stage("posts")
                say(f"Hiring posts from the last {options.post_hours} hours...")
                posts = scrape_posts(page, job, say=say, max_hours=options.post_hours, max_posts=options.max_posts,
                                     debug_dir=debug_dir, now=now)
            if not options.skip_jobs and not posts.interrupted and not posts.blocked:
                stage("jobs")
                say(f"Jobs from the last {options.job_days} days...")
                jobs = scrape_jobs(page, job, location, say=say, days=options.job_days, max_jobs=options.max_jobs,
                                   debug_dir=debug_dir)
    except (BrowserNotFound, BrowserDownloadFailed, BrowserProblem) as err:
        return _failed(str(err), 2)
    except ScrapeStopped as stop:
        return _failed(str(stop), 1)
    except (KeyboardInterrupt, Cancelled):
        if not (posts.items or jobs.items):
            return _failed("Stopped. Nothing was collected.", 1)
        notes.append("Stopped before the end.")
    except Exception as err:  # a bug or a crashed browser: keep whatever was collected
        error = f"Something went wrong: {first_line(err)}"
        if not (posts.items or jobs.items):
            return _failed(error, 1)
        notes.append(error)

    if posts.stopped:
        notes.append(f"Post search stopped early: {posts.stopped}")
    if jobs.stopped:
        notes.append(f"Jobs search stopped early: {jobs.stopped}")
    if options.skip_posts:
        notes.append("Post search was skipped.")
    if options.skip_jobs:
        notes.append("Jobs search was skipped.")
    elif posts.interrupted:
        notes.append("Jobs search didn't run because the run was stopped.")
    elif posts.blocked:
        notes.append("Jobs search didn't run because LinkedIn pushed back. Try again in an hour or so.")

    stage("saving")
    write_results(out_dir, job=job, location=location, run_at=now, post_hours=options.post_hours,
                  job_days=options.job_days, posts=posts.items, jobs=jobs.items, now=now, notes=notes)
    return RunOutcome(out_dir, posts.items, jobs.items, notes, error, 0)
```

- [ ] **Step 4: Put `cli.py` on top of the runner**

Replace `peerpatch_linkedin/cli.py` with:
```python
"""Command line: run one search in the terminal."""
from __future__ import annotations

import argparse
import sys
import webbrowser
from pathlib import Path
from typing import Callable

from . import config
from .browsers import KEYS
from .runner import MAX_POST_HOURS, RunOutcome, SearchOptions, run_search


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="peerpatch_linkedin",
        description="Collect LinkedIn hiring posts (last 48 hours) and job listings (last 7 days) for a job title.",
    )
    parser.add_argument("--job", help='job title to search for, e.g. "data analyst"')
    parser.add_argument("--location", help="location for the jobs search (default: India; \"\" for anywhere)")
    parser.add_argument("--browser", choices=KEYS, default="auto",
                        help="browser to drive (default: Chrome, then Edge, then Brave, else the built-in one)")
    parser.add_argument("--max-posts", type=int, default=100, help="stop after this many hiring posts (default 100)")
    parser.add_argument("--max-jobs", type=int, default=200, help="stop after this many jobs (default 200)")
    parser.add_argument("--post-hours", type=int, default=48, help="how far back posts go, 1 to 168 (default 48)")
    parser.add_argument("--job-days", type=int, default=7, help="how far back jobs go (default 7)")
    parser.add_argument("--skip-posts", action="store_true", help="only search jobs")
    parser.add_argument("--skip-jobs", action="store_true", help="only search posts")
    parser.add_argument("--debug", action="store_true", help="save the raw pages into the results folder")
    parser.add_argument("--no-open", action="store_true", help="don't open the report or the page")
    parser.add_argument("--port", type=int, default=8765, help="port for the web page (default 8765)")
    parser.add_argument("--profile-dir", type=Path, default=config.TOOL_DIR,
                        help="folder that holds browser-profiles, where each browser keeps its LinkedIn login "
                             "(default: next to this tool)")
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


def options_from_args(args: argparse.Namespace, job: str, location: str) -> SearchOptions:
    return SearchOptions(
        job=job, location=location, browser=args.browser, max_posts=args.max_posts, max_jobs=args.max_jobs,
        post_hours=args.post_hours, job_days=args.job_days, skip_posts=args.skip_posts, skip_jobs=args.skip_jobs,
        debug=args.debug, profile_base=args.profile_dir, results_dir=args.results_dir,
    )


def report_outcome(outcome: RunOutcome, open_report: bool) -> int:
    if outcome.out_dir is None:
        say(outcome.error or "Nothing was saved.")
        return outcome.exit_code
    for note in outcome.notes:
        say(note)
    say(f"\nDone. {len(outcome.posts)} hiring posts, {len(outcome.jobs)} jobs.")
    say(f"Saved in: {outcome.out_dir}")
    if open_report:
        webbrowser.open(outcome.report.resolve().as_uri())
    return outcome.exit_code


def main(argv: list[str] | None = None, ask: Callable[[str], str] = input) -> int:
    make_console_safe()
    args = parse_args(argv)
    clamp_limits(args, say)
    try:
        job, location = resolve_search(args, ask)
    except (EOFError, KeyboardInterrupt):
        say("\nNo job title given. Nothing to do.")
        return 2
    outcome = run_search(options_from_args(args, job, location), say)
    return report_outcome(outcome, open_report=not args.no_open)
```

- [ ] **Step 5: Run the whole suite**

Run: `.venv/bin/pytest -q`
Expected: all pass. `tests/test_e2e.py` is the regression check that `run_search` behaves like the old `main`.

- [ ] **Step 6: Commit**

```bash
git add peerpatch_linkedin/runner.py peerpatch_linkedin/cli.py tests/test_runner.py tests/test_cli.py
git commit -m "Move the run into runner.run_search; add --browser and --port"
```

---

### Task 4: The local server (`web.py`) and web mode in the CLI

**Files:**
- Create: `peerpatch_linkedin/web.py`
- Create: `peerpatch_linkedin/static/index.html` (placeholder now, real page in Task 5)
- Create: `tests/web_client.py`, `tests/test_web.py`
- Modify: `peerpatch_linkedin/cli.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: `runner.SearchOptions`, `runner.RunOutcome`, `runner.run_search`, `runner.validate`; `browser.request_stop`, `browser.first_line`; `browsers.KEYS`, `browsers.default_browser`, `browsers.find_browsers`
- Produces (in `web.py`):
  - `class RunState` with `begin() -> bool`, `add_log(line)`, `set_stage(name)`, `finish(result: dict)`, `snapshot(since=0) -> dict`
  - `parse_start(payload, results_dir, profile_base) -> SearchOptions | str`
  - `list_runs(results_dir, limit=50) -> list[dict]`
  - `outcome_summary(outcome) -> dict`
  - `class App(*, token, results_dir, profile_base, run=run_search, browsers=find_browsers)` with `browsers_payload()`, `start(payload) -> (status, dict)`, `stop() -> dict`, `.state: RunState`
  - `make_server(app, port=8765) -> ThreadingHTTPServer`
  - `serve(*, port=8765, open_page=True, results_dir, profile_base, say=print) -> int`
  - in `cli.py`: `job_and_location(args) -> tuple[str, str]`; `main(argv=None) -> int` (no `ask`)
- Produces (tests): `tests.web_client`: `TOKEN`, `FOLDER`, `NOW`, `fake_browsers()`, `fake_run(gate=None, error=None, stage_name="posts")`, `WebServer(app)` with `.base`, `.call(method, path, body=None, token=TOKEN, headers=None) -> (status, bytes, headers)`, `.json(...) -> (status, data)`, `.wait_until_done(timeout=60) -> dict`, `.close()`

- [ ] **Step 1: Write the test helpers and failing tests**

`tests/web_client.py`:
```python
"""Start the PeerPatch web server in a thread and call it, bypassing any HTTP proxy."""
from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

from peerpatch_linkedin.browsers import BrowserInfo
from peerpatch_linkedin.report import write_results
from peerpatch_linkedin.runner import RunOutcome
from peerpatch_linkedin.web import App, make_server

TOKEN = "secret-token"
NOW = datetime(2026, 11, 15, 10, 30, tzinfo=timezone.utc)
FOLDER = "data-analyst_2026-11-15_1030"
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def fake_browsers():
    return [BrowserInfo("edge", "Edge", "msedge.exe", True), BrowserInfo("builtin", "Built-in browser", None, False)]


def fake_run(gate=None, error=None, stage_name="posts"):
    """A stand-in for run_search: logs a line, optionally waits for `gate`, then saves an empty result."""
    def run(options, say, stage):
        stage(stage_name)
        say(f"Looking for {options.job}")
        if gate is not None:
            gate.wait(10)
        if error:
            return RunOutcome(None, [], [], [], error, 1)
        out = options.results_dir / FOLDER
        write_results(out, job=options.job, location=options.location, run_at=NOW, post_hours=options.post_hours,
                      job_days=options.job_days, posts=[], jobs=[], now=NOW, notes=["A note"])
        return RunOutcome(out, [], [], ["A note"], None, 0)
    return run


class WebServer:
    def __init__(self, app: App):
        self.app = app
        self.httpd = make_server(app, 0)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.httpd.server_port}"
        self._closed = False

    def call(self, method, path, body=None, token=TOKEN, headers=None):
        data = None if body is None else (body if isinstance(body, bytes) else json.dumps(body).encode())
        request = urllib.request.Request(self.base + path, data=data, method=method)
        if token:
            request.add_header("X-PeerPatch-Token", token)
        if data is not None:
            request.add_header("Content-Type", "application/json")
        for key, value in (headers or {}).items():
            request.add_header(key, value)
        try:
            with _OPENER.open(request, timeout=10) as response:
                return response.status, response.read(), response.headers
        except urllib.error.HTTPError as err:
            return err.code, err.read(), err.headers

    def json(self, method, path, body=None, **kwargs):
        status, raw, _ = self.call(method, path, body, **kwargs)
        return status, json.loads(raw.decode() or "null")

    def wait_until_done(self, timeout=60):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            _, status = self.json("GET", "/api/status")
            if status["state"] == "done":
                return status
            time.sleep(0.1)
        raise AssertionError("the run didn't finish in time")

    def close(self):
        if not self._closed:
            self._closed = True
            self.httpd.shutdown()
            self.httpd.server_close()
```

`tests/test_web.py`:
```python
import socket
import threading

import pytest

from peerpatch_linkedin.browser import clear_stop, stop_requested
from peerpatch_linkedin.web import App, make_server
from tests.web_client import FOLDER, TOKEN, WebServer, fake_browsers, fake_run


def make_app(tmp_path, **kwargs):
    return App(token=TOKEN, results_dir=tmp_path / "results", profile_base=tmp_path, run=fake_run(**kwargs),
               browsers=fake_browsers)


@pytest.fixture
def web(tmp_path):
    server = WebServer(make_app(tmp_path))
    yield server
    server.close()


def test_page_loads_without_a_token_but_the_api_needs_one(web):
    status, body, headers = web.call("GET", "/", token=None)
    assert status == 200 and headers["Content-Type"].startswith("text/html")
    assert web.json("GET", "/api/status", token=None)[0] == 403
    assert web.json("GET", "/api/status", token="wrong")[0] == 403


def test_another_host_name_is_refused(web):
    port = web.httpd.server_port
    assert web.call("GET", "/", headers={"Host": f"evil.example:{port}"})[0] == 403
    assert web.call("GET", "/api/status", headers={"Host": f"localhost:{port}"})[0] == 200


def test_browsers_payload(web):
    assert web.json("GET", "/api/browsers") == (200, {
        "default": "edge",
        "browsers": [{"key": "edge", "label": "Edge", "installed": True},
                     {"key": "builtin", "label": "Built-in browser", "installed": False}],
    })


def test_start_then_status_then_files(web):
    assert web.json("POST", "/api/start", {"job": "data analyst"}) == (202, {"ok": True})
    status = web.wait_until_done()
    assert status["log"] == ["Looking for data analyst"]
    assert status["result"] == {"folder": FOLDER, "posts": 0, "jobs": 0, "notes": ["A note"], "error": None}
    code, body, headers = web.call("GET", f"/results/{FOLDER}/posts.csv")
    assert code == 200
    assert headers["Content-Disposition"] == f'attachment; filename="{FOLDER}_posts.csv"'
    assert body.startswith(b"\xef\xbb\xbfposted_at,")
    assert web.call("GET", f"/results/{FOLDER}/report.html", token=None, headers={})[0] == 403
    assert web.call("GET", f"/results/{FOLDER}/report.html?t={TOKEN}", token=None)[0] == 200
    assert web.json("GET", "/api/runs") == (200, [{"folder": FOLDER, "posts": 0, "jobs": 0}])


def test_status_since_sends_only_new_lines(web):
    web.json("POST", "/api/start", {"job": "x"})
    web.wait_until_done()
    _, status = web.json("GET", "/api/status?since=1")
    assert status["log"] == [] and status["log_size"] == 1


def test_a_second_start_while_running_is_refused(tmp_path):
    gate = threading.Event()
    server = WebServer(make_app(tmp_path, gate=gate))
    try:
        assert server.json("POST", "/api/start", {"job": "x"})[0] == 202
        status, data = server.json("POST", "/api/start", {"job": "y"})
        assert status == 409 and "already running" in data["error"]
    finally:
        gate.set()
        server.close()


@pytest.mark.parametrize("body, message", [
    ({"job": "  "}, "Type a job title."),
    ({"job": "x", "post_hours": 500}, "Post hours must be 1 to 168."),
    ({"job": "x", "browser": "safari"}, "Unknown browser 'safari'."),
    ({"job": "x", "max_jobs": "lots"}, "'max_jobs' must be a whole number."),
    (b"not json", "Send the search as JSON."),
])
def test_bad_searches_are_refused_with_a_message(web, body, message):
    assert web.json("POST", "/api/start", body) == (400, {"error": message})


def test_stop_asks_the_run_to_stop(web):
    try:
        assert web.json("POST", "/api/stop") == (200, {"ok": True})
        assert stop_requested()
    finally:
        clear_stop()


def test_a_failed_run_reports_its_error(tmp_path):
    server = WebServer(make_app(tmp_path, error="No LinkedIn login seen in time."))
    try:
        server.json("POST", "/api/start", {"job": "x"})
        result = server.wait_until_done()["result"]
        assert (result["folder"], result["error"]) == (None, "No LinkedIn login seen in time.")
    finally:
        server.close()


@pytest.mark.parametrize("path", [
    "/results/../x", f"/results/{FOLDER}/notes.txt", "/results/%2e%2e/posts.csv", "/results/missing/posts.csv",
    f"/results/{FOLDER}/../{FOLDER}/posts.csv",
])
def test_only_result_files_can_be_fetched(web, path):
    web.json("POST", "/api/start", {"job": "x"})
    web.wait_until_done()
    assert web.call("GET", path)[0] == 404


def test_busy_port_moves_to_the_next_one(tmp_path):
    blocker = socket.socket()
    blocker.bind(("127.0.0.1", 0))
    blocker.listen(1)
    taken = blocker.getsockname()[1]
    try:
        httpd = make_server(make_app(tmp_path), taken)
        try:
            assert httpd.server_port != taken
        finally:
            httpd.server_close()
    finally:
        blocker.close()
```

In `tests/test_cli.py`:
- change the import line to `from peerpatch_linkedin.cli import clamp_limits, job_and_location, make_console_safe, parse_args`
- delete `test_job_flag_means_no_questions_and_india_by_default`, `test_asks_until_a_job_is_typed_then_defaults_location`, `test_typed_location_is_kept` and `test_blank_location_flag_means_anywhere`
- append:
```python
def test_job_and_location():
    assert job_and_location(parse_args(["--job", " data analyst "])) == ("data analyst", "India")
    assert job_and_location(parse_args(["--job", "x", "--location", " Pune "])) == ("x", "Pune")
    assert job_and_location(parse_args(["--job", "x", "--location", ""])) == ("x", "")
    assert job_and_location(parse_args([])) == ("", "India")


def test_no_job_starts_the_web_page(monkeypatch, tmp_path):
    from peerpatch_linkedin import cli

    calls = []
    monkeypatch.setattr(cli, "serve", lambda **kwargs: calls.append(kwargs) or 0)
    assert cli.main(["--no-open", "--port", "9001", "--results-dir", str(tmp_path)]) == 0
    assert calls[0]["port"] == 9001 and calls[0]["open_page"] is False and calls[0]["results_dir"] == tmp_path
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_web.py tests/test_cli.py -q`
Expected: `test_web.py` fails to import (`No module named 'peerpatch_linkedin.web'`). `test_cli.py` fails to import `job_and_location`.

- [ ] **Step 3: Write `web.py` and a placeholder page**

`peerpatch_linkedin/static/index.html` (replaced in Task 5):
```html
<!doctype html><html lang="en"><head><meta charset="utf-8"><title>PeerPatch LinkedIn</title></head><body><main><h1>LinkedIn job search</h1></main></body></html>
```

`peerpatch_linkedin/web.py`:
```python
"""The local web page: a small server on 127.0.0.1 that runs one search at a time."""
from __future__ import annotations

import csv
import json
import secrets
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, unquote, urlparse

from .browser import first_line, request_stop
from .browsers import KEYS, default_browser, find_browsers
from .runner import RunOutcome, SearchOptions, run_search, validate

STATIC_DIR = Path(__file__).with_name("static")
RESULT_FILES = {
    "report.html": "text/html; charset=utf-8",
    "posts.csv": "text/csv; charset=utf-8",
    "jobs.csv": "text/csv; charset=utf-8",
}
PORT_TRIES = 20
MAX_BODY = 10_000


class RunState:
    """What the page polls. The worker thread writes it; request threads read it."""

    def __init__(self):
        self._lock = threading.Lock()
        self.state = "idle"
        self.stage = ""
        self.log: list[str] = []
        self.result: dict | None = None

    def begin(self) -> bool:
        with self._lock:
            if self.state == "running":
                return False
            self.state, self.stage, self.log, self.result = "running", "starting", [], None
            return True

    def add_log(self, line: str) -> None:
        with self._lock:
            self.log.append(line)

    def set_stage(self, stage: str) -> None:
        with self._lock:
            self.stage = stage

    def finish(self, result: dict) -> None:
        with self._lock:
            self.state, self.stage, self.result = "done", "done", result

    def snapshot(self, since: int = 0) -> dict:
        with self._lock:
            since = max(0, min(since, len(self.log)))
            return {"state": self.state, "stage": self.stage, "log": self.log[since:], "log_size": len(self.log),
                    "result": self.result}


def _whole_number(payload: dict, name: str, default: int) -> int:
    value = payload.get(name, default)
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError(name)
    try:
        return int(value)
    except ValueError:
        raise ValueError(name) from None


def parse_start(payload, results_dir: Path, profile_base: Path) -> SearchOptions | str:
    if not isinstance(payload, dict):
        return "Send the search as JSON."
    browser = str(payload.get("browser") or "auto").lower()
    if browser not in KEYS:
        return f"Unknown browser '{browser}'."
    try:
        options = SearchOptions(
            job=str(payload.get("job") or "").strip(),
            location=str(payload.get("location", "India") or "").strip(),
            browser=browser,
            max_posts=_whole_number(payload, "max_posts", 100),
            max_jobs=_whole_number(payload, "max_jobs", 200),
            post_hours=_whole_number(payload, "post_hours", 48),
            job_days=_whole_number(payload, "job_days", 7),
            skip_posts=bool(payload.get("skip_posts")),
            skip_jobs=bool(payload.get("skip_jobs")),
            debug=bool(payload.get("debug")),
            profile_base=profile_base,
            results_dir=results_dir,
        )
    except ValueError as err:
        return f"'{err}' must be a whole number."
    return validate(options) or options


def _count_rows(path: Path) -> int:
    try:
        with open(path, encoding="utf-8-sig", newline="") as handle:
            return max(0, sum(1 for _ in csv.reader(handle)) - 1)
    except OSError:
        return 0


def list_runs(results_dir: Path, limit: int = 50) -> list[dict]:
    if not results_dir.is_dir():
        return []
    folders = [p for p in results_dir.iterdir() if p.is_dir() and (p / "report.html").is_file()]
    folders.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return [{"folder": p.name, "posts": _count_rows(p / "posts.csv"), "jobs": _count_rows(p / "jobs.csv")}
            for p in folders[:limit]]


def outcome_summary(outcome: RunOutcome) -> dict:
    return {"folder": outcome.out_dir.name if outcome.out_dir else None, "posts": len(outcome.posts),
            "jobs": len(outcome.jobs), "notes": list(outcome.notes), "error": outcome.error}


class App:
    def __init__(self, *, token: str, results_dir: Path, profile_base: Path, run: Callable = run_search,
                 browsers: Callable = find_browsers):
        self.token = token
        self.results_dir = results_dir
        self.profile_base = profile_base
        self.run = run
        self.browsers = browsers
        self.state = RunState()

    def browsers_payload(self) -> dict:
        found = self.browsers()
        return {"default": default_browser(found).key,
                "browsers": [{"key": b.key, "label": b.label, "installed": b.installed} for b in found]}

    def start(self, payload) -> tuple[int, dict]:
        options = parse_start(payload, self.results_dir, self.profile_base)
        if isinstance(options, str):
            return 400, {"error": options}
        if not self.state.begin():
            return 409, {"error": "A search is already running. Wait for it to finish or press Stop."}
        threading.Thread(target=self._work, args=(options,), daemon=True).start()
        return 202, {"ok": True}

    def _work(self, options: SearchOptions) -> None:
        try:
            summary = outcome_summary(self.run(options, say=self.state.add_log, stage=self.state.set_stage))
        except Exception as err:  # run_search catches its own errors; this is the last line of defence
            summary = {"folder": None, "posts": 0, "jobs": 0, "notes": [],
                       "error": f"Something went wrong: {first_line(err)}"}
        self.state.finish(summary)

    def stop(self) -> dict:
        request_stop()
        return {"ok": True}


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    # On Windows SO_REUSEADDR lets a second server bind the same port, so a second launch
    # would silently share it. Elsewhere it only skips TIME_WAIT, which is what we want.
    allow_reuse_address = not sys.platform.startswith("win")


def make_handler(app: App):
    class Handler(BaseHTTPRequestHandler):
        server_version = "PeerPatch"

        def log_message(self, *args):  # keep the terminal quiet
            pass

        def do_GET(self):
            self._route("GET")

        def do_POST(self):
            self._route("POST")

        def _send(self, status: int, body: bytes, content_type: str, extra: dict | None = None) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            for key, value in (extra or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: int, data) -> None:
            self._send(status, json.dumps(data).encode("utf-8"), "application/json")

        def _host_ok(self) -> bool:
            port = self.server.server_port
            return self.headers.get("Host", "") in (f"127.0.0.1:{port}", f"localhost:{port}")

        def _token_ok(self, query: dict) -> bool:
            given = self.headers.get("X-PeerPatch-Token") or query.get("t", [""])[0]
            return secrets.compare_digest(given.encode("utf-8"), app.token.encode("utf-8"))

        def _read_json(self):
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                return None
            if length <= 0 or length > MAX_BODY:
                return None
            try:
                return json.loads(self.rfile.read(length).decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                return None

        def _route(self, method: str) -> None:
            url = urlparse(self.path)
            query = parse_qs(url.query)
            if not self._host_ok():
                return self._json(403, {"error": "Wrong host."})
            if method == "GET" and url.path == "/":
                return self._send(200, (STATIC_DIR / "index.html").read_bytes(), "text/html; charset=utf-8")
            if method == "GET" and url.path == "/favicon.ico":
                return self._send(204, b"", "image/x-icon")
            if not self._token_ok(query):
                return self._json(403, {"error": "Open the link from the PeerPatch terminal window."})
            if method == "GET" and url.path == "/api/browsers":
                return self._json(200, app.browsers_payload())
            if method == "GET" and url.path == "/api/status":
                try:
                    since = int(query.get("since", ["0"])[0])
                except ValueError:
                    since = 0
                return self._json(200, app.state.snapshot(since))
            if method == "GET" and url.path == "/api/runs":
                return self._json(200, list_runs(app.results_dir))
            if method == "POST" and url.path == "/api/start":
                status, data = app.start(self._read_json())
                return self._json(status, data)
            if method == "POST" and url.path == "/api/stop":
                return self._json(200, app.stop())
            if method == "GET" and url.path.startswith("/results/"):
                return self._result_file(url.path)
            return self._json(404, {"error": "Not found."})

        def _result_file(self, path: str) -> None:
            parts = [unquote(p) for p in path.split("/")[2:]]
            if len(parts) != 2 or parts[1] not in RESULT_FILES:
                return self._json(404, {"error": "Not found."})
            folder, name = parts
            if folder in ("", ".", "..") or "/" in folder or "\\" in folder:
                return self._json(404, {"error": "Not found."})
            target = app.results_dir / folder / name
            if target.parent.parent.resolve() != app.results_dir.resolve() or not target.is_file():
                return self._json(404, {"error": "Not found."})
            extra = {"Content-Disposition": f'attachment; filename="{folder}_{name}"'} if name.endswith(".csv") else {}
            return self._send(200, target.read_bytes(), RESULT_FILES[name], extra)

    return Handler


def make_server(app: App, port: int = 8765) -> ThreadingHTTPServer:
    """Listen on 127.0.0.1: the given port, the next free one up to PORT_TRIES later, or any free port."""
    handler = make_handler(app)
    candidates = [0] if port == 0 else [*range(port, port + PORT_TRIES), 0]
    for candidate in candidates:
        try:
            return _Server(("127.0.0.1", candidate), handler)
        except OSError:
            continue
    raise OSError("No free port for the PeerPatch page.")


def serve(*, port: int = 8765, open_page: bool = True, results_dir: Path, profile_base: Path,
          say: Callable[[str], None] = print) -> int:
    find_browsers()  # looks up the built-in browser once, on this thread, before any request needs it
    app = App(token=secrets.token_urlsafe(16), results_dir=results_dir, profile_base=profile_base)
    server = make_server(app, port)
    url = f"http://127.0.0.1:{server.server_port}/?t={app.token}"
    say("PeerPatch is running. Your browser should open by itself.")
    say(f"If it doesn't, open this link: {url}")
    say("Leave this window open while you use the page. Close it to stop.")
    if open_page:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        say("\nStopped.")
    finally:
        request_stop()
        server.server_close()
    return 0
```

- [ ] **Step 4: Switch the CLI to web mode when there's no `--job`**

In `peerpatch_linkedin/cli.py`:
- change the module docstring to `"""Command line: no --job opens the web page; --job runs one search in the terminal."""`
- remove `from typing import Callable`'s use in `resolve_search` by deleting `resolve_search` entirely, and add `from .web import serve` after the runner import
- add after `parse_args`:
```python
def job_and_location(args: argparse.Namespace) -> tuple[str, str]:
    location = "India" if args.location is None else args.location
    return (args.job or "").strip(), location.strip()
```
- replace `main` with:
```python
def main(argv: list[str] | None = None) -> int:
    make_console_safe()
    args = parse_args(argv)
    job, location = job_and_location(args)
    if not job:
        return serve(port=args.port, open_page=not args.no_open, results_dir=args.results_dir,
                     profile_base=args.profile_dir, say=say)
    clamp_limits(args, say)
    outcome = run_search(options_from_args(args, job, location), say)
    return report_outcome(outcome, open_report=not args.no_open)
```
(`Callable` is still used by `clamp_limits`, so keep the `typing` import.)

- [ ] **Step 5: Run the whole suite**

Run: `.venv/bin/pytest -q`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add peerpatch_linkedin/web.py peerpatch_linkedin/static/index.html peerpatch_linkedin/cli.py tests/web_client.py tests/test_web.py tests/test_cli.py
git commit -m "Add the local web server; no --job now opens the page"
```

---

### Task 5: The page (`static/index.html`)

**Files:**
- Modify: `peerpatch_linkedin/static/index.html` (whole file)
- Create: `tests/test_page.py`

**Interfaces:**
- Consumes: the API from Task 4; `tests.web_client` helpers; the `page` fixture from `tests/conftest.py`
- Produces: element IDs the tests use: `#no-token`, `#gone`, `#form-view`, `#job`, `#location`, `#browser` (options carry `data-label`), `#form-error`, `#runs`, `#no-runs`, `#running`, `#stage`, `#login-banner`, `#log`, `#stop`, `#stopping`, `#done`, `#summary`, `#notes`, `#run-error`, `#dl-posts`, `#dl-jobs`, `#open-report`, `#again`, `#report-frame`

- [ ] **Step 1: Write the failing tests**

`tests/test_page.py`:
```python
import threading
import time

from playwright.sync_api import expect

from peerpatch_linkedin.browser import clear_stop, stop_requested
from peerpatch_linkedin.web import App
from tests.web_client import FOLDER, TOKEN, WebServer, fake_browsers, fake_run


def make_web(tmp_path, **kwargs):
    return WebServer(App(token=TOKEN, results_dir=tmp_path / "results", profile_base=tmp_path,
                         run=fake_run(**kwargs), browsers=fake_browsers))


def open_page(page, web):
    page.goto(f"{web.base}/?t={TOKEN}")
    expect(page.locator("#form-view")).to_be_visible()


def test_search_from_the_page_to_the_results(page, tmp_path):
    web = make_web(tmp_path)
    try:
        open_page(page, web)
        expect(page.locator("#browser")).to_have_value("edge")
        expect(page.locator("#browser option")).to_have_text(
            ["Edge (installed)", "Built-in browser (downloads once, about 150 MB)"])
        expect(page.locator("#no-runs")).to_be_visible()
        page.get_by_label("Job title").fill("data analyst")
        page.get_by_role("button", name="Start").click()
        expect(page.locator("#done")).to_be_visible(timeout=10_000)
        expect(page.locator("#summary")).to_have_text("0 hiring posts, 0 jobs")
        expect(page.locator("#notes")).to_contain_text("A note")
        expect(page.locator("#log")).to_contain_text("Looking for data analyst")
        assert page.locator("#dl-posts").get_attribute("href") == f"/results/{FOLDER}/posts.csv?t={TOKEN}"
        assert page.locator("#report-frame").get_attribute("src") == f"/results/{FOLDER}/report.html?t={TOKEN}"
        page.get_by_role("button", name="New search").click()
        expect(page.locator("#form-view")).to_be_visible()
        expect(page.locator("#runs")).to_contain_text(FOLDER)
        expect(page.get_by_label("Job title")).to_have_value("data analyst")
    finally:
        web.close()


def test_page_without_the_token_says_where_to_find_the_link(page, tmp_path):
    web = make_web(tmp_path)
    try:
        page.goto(f"{web.base}/")
        expect(page.locator("#no-token")).to_be_visible()
        expect(page.locator("#form-view")).to_be_hidden()
    finally:
        web.close()


def test_an_empty_job_title_shows_the_server_message(page, tmp_path):
    web = make_web(tmp_path)
    try:
        open_page(page, web)
        page.get_by_role("button", name="Start").click()
        expect(page.locator("#form-error")).to_have_text("Type a job title.")
    finally:
        web.close()


def test_a_failed_run_offers_try_again(page, tmp_path):
    web = make_web(tmp_path, error="No LinkedIn login seen in time.")
    try:
        open_page(page, web)
        page.get_by_label("Job title").fill("data analyst")
        page.get_by_role("button", name="Start").click()
        expect(page.locator("#run-error")).to_have_text("No LinkedIn login seen in time.")
        expect(page.locator("#dl-posts")).to_be_hidden()
        page.get_by_role("button", name="Try again").click()
        expect(page.locator("#form-view")).to_be_visible()
    finally:
        web.close()


def test_reopening_the_link_during_a_run_shows_its_progress(page, tmp_path):
    gate = threading.Event()
    web = make_web(tmp_path, gate=gate, stage_name="waiting-for-login")
    try:
        assert web.call("POST", "/api/start", {"job": "data analyst"})[0] == 202
        page.goto(f"{web.base}/?t={TOKEN}")
        expect(page.locator("#running")).to_be_visible()
        expect(page.locator("#log")).to_contain_text("Looking for data analyst")
        expect(page.locator("#login-banner")).to_contain_text("Log in to LinkedIn")
        gate.set()
        expect(page.locator("#done")).to_be_visible(timeout=10_000)
    finally:
        gate.set()
        web.close()


def test_stop_button_asks_the_search_to_stop(page, tmp_path):
    gate = threading.Event()
    web = make_web(tmp_path, gate=gate)
    try:
        open_page(page, web)
        page.get_by_label("Job title").fill("data analyst")
        page.get_by_role("button", name="Start").click()
        expect(page.locator("#running")).to_be_visible()
        page.get_by_role("button", name="Stop").click()
        expect(page.locator("#stopping")).to_be_visible()
        deadline = time.monotonic() + 5
        while not stop_requested() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert stop_requested()
    finally:
        clear_stop()
        gate.set()
        web.close()


def test_closing_peerpatch_shows_that_it_stopped(page, tmp_path):
    web = make_web(tmp_path)
    open_page(page, web)
    web.close()
    page.get_by_label("Job title").fill("data analyst")
    page.get_by_role("button", name="Start").click()
    expect(page.locator("#gone")).to_be_visible()


def test_job_title_with_markup_is_shown_as_text(page, tmp_path):
    web = make_web(tmp_path)
    try:
        open_page(page, web)
        page.get_by_label("Job title").fill("<b>boss</b>")
        page.get_by_role("button", name="Start").click()
        expect(page.locator("#done")).to_be_visible(timeout=10_000)
        expect(page.locator("#log")).to_contain_text("Looking for <b>boss</b>")
        assert page.locator("#log b").count() == 0
    finally:
        web.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_page.py -q`
Expected: every test fails (the placeholder page has none of the elements; the first failure is `#form-view` not found).

- [ ] **Step 3: Write `static/index.html`**

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PeerPatch LinkedIn</title>
<style>
:root { --bg: #f7f6f2; --card: #ffffff; --text: #1d1d1b; --muted: #6b6a66; --line: #e2e0d9; --accent: #0a66c2; --accent-text: #ffffff; --soft: #e8f1fb; --warn: #fff4d6; --warn-line: #e7c66b; --bad: #fde8e8; }
@media (prefers-color-scheme: dark) {
  :root { --bg: #161615; --card: #20201e; --text: #ecebe6; --muted: #a3a29c; --line: #34332f; --accent: #70b5f9; --accent-text: #0b1a2a; --soft: #1d2c3d; --warn: #3a3016; --warn-line: #8a6d1f; --bad: #3b1f1f; }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--text); font: 15px/1.5 -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
main { max-width: 860px; margin: 0 auto; padding: 24px 16px 64px; }
h1 { font-size: 24px; margin: 0 0 4px; }
h2 { font-size: 18px; margin: 28px 0 10px; }
.sub { color: var(--muted); margin: 0 0 20px; }
.card { background: var(--card); border: 1px solid var(--line); border-radius: 12px; padding: 18px; }
label { display: block; font-weight: 600; margin: 12px 0 4px; }
input[type=text], input[type=number], select { width: 100%; padding: 10px 12px; font: inherit; color: var(--text); background: var(--bg); border: 1px solid var(--line); border-radius: 8px; }
.row { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 0 12px; }
label.check { display: flex; gap: 8px; align-items: center; font-weight: 400; margin: 8px 0; }
details { margin-top: 14px; }
summary { cursor: pointer; color: var(--accent); }
button, a.button { display: inline-block; font: inherit; padding: 10px 18px; border-radius: 8px; border: 1px solid var(--line); background: var(--card); color: var(--text); cursor: pointer; text-decoration: none; }
button.primary { background: var(--accent); color: var(--accent-text); border-color: var(--accent); font-weight: 600; }
button:disabled { opacity: 0.6; cursor: default; }
.actions { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 16px; align-items: center; }
.error { background: var(--bad); border-radius: 8px; padding: 10px 12px; margin: 12px 0; }
.banner { background: var(--warn); border: 1px solid var(--warn-line); border-radius: 10px; padding: 12px 14px; font-weight: 600; margin: 12px 0; }
.stage { font-size: 17px; font-weight: 600; margin: 0 0 8px; }
#log { background: var(--bg); border: 1px solid var(--line); border-radius: 8px; padding: 10px 12px; font: 13px/1.5 ui-monospace, Menlo, Consolas, monospace; white-space: pre-wrap; overflow-wrap: anywhere; max-height: 320px; overflow: auto; margin: 0; }
.note { background: var(--soft); border-radius: 8px; padding: 8px 12px; margin: 6px 0; }
iframe { display: block; width: 100%; height: 70vh; border: 1px solid var(--line); border-radius: 10px; margin-top: 16px; background: var(--card); }
#runs { list-style: none; padding: 0; margin: 0; }
#runs li { padding: 8px 0; border-bottom: 1px solid var(--line); display: flex; flex-wrap: wrap; gap: 4px 12px; align-items: baseline; }
#runs .name { font-weight: 600; overflow-wrap: anywhere; }
.muted { color: var(--muted); }
a { color: var(--accent); }
[hidden] { display: none !important; }
</style>
</head>
<body>
<main>
  <h1>LinkedIn job search</h1>
  <p class="sub">Hiring posts from the last 2 days and job listings from the last 7 days.</p>

  <div id="no-token" class="error" hidden>Open the link from the PeerPatch terminal window. It ends in <code>?t=</code> and a code.</div>
  <div id="gone" class="error" hidden>PeerPatch has stopped. Start it again from run.bat or run.command, then open the new link.</div>

  <section id="form-view" hidden>
    <form id="search" class="card" novalidate>
      <label for="job">Job title</label>
      <input id="job" type="text" placeholder="data analyst" autocomplete="off">
      <label for="location">Location</label>
      <input id="location" type="text" value="India">
      <label for="browser">Browser</label>
      <select id="browser"></select>
      <details>
        <summary>More options</summary>
        <div class="row">
          <div><label for="max_posts">Max posts</label><input id="max_posts" type="number" min="1" value="100"></div>
          <div><label for="max_jobs">Max jobs</label><input id="max_jobs" type="number" min="1" value="200"></div>
          <div><label for="post_hours">Post hours</label><input id="post_hours" type="number" min="1" max="168" value="48"></div>
          <div><label for="job_days">Job days</label><input id="job_days" type="number" min="1" value="7"></div>
        </div>
        <label class="check"><input id="skip_posts" type="checkbox"> Skip posts</label>
        <label class="check"><input id="skip_jobs" type="checkbox"> Skip jobs</label>
        <label class="check"><input id="debug" type="checkbox"> Save raw pages (for fixing problems)</label>
      </details>
      <div class="actions"><button class="primary" type="submit">Start</button></div>
      <div id="form-error" class="error" hidden></div>
    </form>
    <h2>Past runs</h2>
    <ul id="runs"></ul>
    <p id="no-runs" class="muted">No searches yet.</p>
  </section>

  <section id="running" class="card" hidden>
    <p id="stage" class="stage">Getting the browser ready</p>
    <div id="login-banner" class="banner" hidden></div>
    <pre id="log"></pre>
    <div class="actions">
      <button id="stop" type="button">Stop</button>
      <span id="stopping" class="muted" hidden>Stopping after the current step...</span>
    </div>
  </section>

  <section id="done" hidden>
    <div class="card">
      <p id="summary" class="stage"></p>
      <div id="notes"></div>
      <div id="run-error" class="error" hidden></div>
      <div class="actions">
        <a id="dl-posts" class="button" download>Download posts.csv</a>
        <a id="dl-jobs" class="button" download>Download jobs.csv</a>
        <a id="open-report" class="button" target="_blank" rel="noopener">Open report in new tab</a>
        <button id="again" class="primary" type="button">New search</button>
      </div>
    </div>
    <iframe id="report-frame" title="Report"></iframe>
  </section>
</main>
<script>
(function () {
  "use strict";
  var token = new URLSearchParams(location.search).get("t");
  var STAGES = {
    "starting": "Getting the browser ready",
    "downloading-browser": "Downloading the built-in browser (one time)",
    "waiting-for-login": "Waiting for you to log in",
    "posts": "Searching hiring posts",
    "jobs": "Searching jobs",
    "saving": "Saving",
    "done": "Finishing"
  };
  var logSize = 0;
  var polling = null;
  var browserLabel = "browser";

  function $(id) { return document.getElementById(id); }

  function show(view) {
    ["form-view", "running", "done"].forEach(function (id) { $(id).hidden = id !== view; });
  }

  function plural(n, word) { return n + " " + word + (n === 1 ? "" : "s"); }

  function serverGone() {
    if (polling) { clearInterval(polling); polling = null; }
    $("gone").hidden = false;
  }

  function api(method, path, body) {
    var options = { method: method, headers: { "X-PeerPatch-Token": token } };
    if (body !== undefined) {
      options.headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(body);
    }
    return fetch(path, options).then(function (response) {
      return response.json().catch(function () { return {}; }).then(function (data) {
        if (!response.ok) {
          var error = new Error(data.error || ("HTTP " + response.status));
          error.status = response.status;
          throw error;
        }
        return data;
      });
    }, function (networkError) {
      serverGone();
      throw networkError;
    });
  }

  function fileUrl(folder, name) {
    return "/results/" + encodeURIComponent(folder) + "/" + name + "?t=" + encodeURIComponent(token);
  }

  function loadBrowsers() {
    return api("GET", "/api/browsers").then(function (data) {
      var select = $("browser");
      select.textContent = "";
      data.browsers.forEach(function (b) {
        var option = document.createElement("option");
        option.value = b.key;
        option.dataset.label = b.label;
        option.textContent = (b.key === "builtin" && !b.installed)
          ? b.label + " (downloads once, about 150 MB)"
          : b.label + " (installed)";
        option.selected = b.key === data.default;
        select.appendChild(option);
      });
    });
  }

  function loadRuns() {
    return api("GET", "/api/runs").then(function (runs) {
      var list = $("runs");
      list.textContent = "";
      $("no-runs").hidden = runs.length > 0;
      runs.forEach(function (run) {
        var item = document.createElement("li");
        var name = document.createElement("span");
        name.className = "name";
        name.textContent = run.folder;
        var counts = document.createElement("span");
        counts.className = "muted";
        counts.textContent = plural(run.posts, "post") + ", " + plural(run.jobs, "job");
        item.appendChild(name);
        item.appendChild(counts);
        [["Report", "report.html"], ["posts.csv", "posts.csv"], ["jobs.csv", "jobs.csv"]].forEach(function (pair) {
          var link = document.createElement("a");
          link.textContent = pair[0];
          link.href = fileUrl(run.folder, pair[1]);
          if (pair[1] === "report.html") { link.target = "_blank"; link.rel = "noopener"; }
          else { link.setAttribute("download", ""); }
          item.appendChild(link);
        });
        list.appendChild(item);
      });
    });
  }

  function numberField(id) { return Number($(id).value); }

  function startSearch(event) {
    event.preventDefault();
    $("form-error").hidden = true;
    var select = $("browser");
    var chosen = select.options[select.selectedIndex];
    browserLabel = chosen ? chosen.dataset.label : "browser";
    var body = {
      job: $("job").value,
      location: $("location").value,
      browser: select.value,
      max_posts: numberField("max_posts"),
      max_jobs: numberField("max_jobs"),
      post_hours: numberField("post_hours"),
      job_days: numberField("job_days"),
      skip_posts: $("skip_posts").checked,
      skip_jobs: $("skip_jobs").checked,
      debug: $("debug").checked
    };
    api("POST", "/api/start", body).then(beginRunning, function (error) {
      if (error.status) {
        $("form-error").textContent = error.message;
        $("form-error").hidden = false;
      }
    });
  }

  function beginRunning() {
    logSize = 0;
    $("log").textContent = "";
    $("stopping").hidden = true;
    $("stop").disabled = false;
    $("login-banner").hidden = true;
    $("stage").textContent = STAGES.starting;
    show("running");
    if (!polling) { polling = setInterval(poll, 1000); }
    poll();
  }

  function poll() {
    api("GET", "/api/status?since=" + logSize).then(render, function () {});
  }

  function render(status) {
    if (status.log.length) {
      $("log").textContent += status.log.join("\n") + "\n";
      $("log").scrollTop = $("log").scrollHeight;
    }
    logSize = status.log_size;
    if (status.state === "running") {
      $("stage").textContent = STAGES[status.stage] || STAGES.starting;
      var waiting = status.stage === "waiting-for-login";
      $("login-banner").hidden = !waiting;
      if (waiting) {
        $("login-banner").textContent = "Log in to LinkedIn in the " + browserLabel +
          " window that just opened. The search starts by itself once you're in.";
      }
    } else if (status.state === "done" && polling) {
      clearInterval(polling);
      polling = null;
      showDone(status.result);
    }
  }

  function showDone(result) {
    show("done");
    var notes = $("notes");
    notes.textContent = "";
    (result.notes || []).forEach(function (text) {
      var line = document.createElement("p");
      line.className = "note";
      line.textContent = text;
      notes.appendChild(line);
    });
    var failed = !result.folder;
    $("run-error").textContent = result.error || "";
    $("run-error").hidden = !result.error;
    $("summary").textContent = failed ? "Nothing was saved." :
      plural(result.posts, "hiring post") + ", " + plural(result.jobs, "job");
    ["dl-posts", "dl-jobs", "open-report", "report-frame"].forEach(function (id) { $(id).hidden = failed; });
    if (failed) {
      $("report-frame").removeAttribute("src");
    } else {
      $("dl-posts").setAttribute("href", fileUrl(result.folder, "posts.csv"));
      $("dl-jobs").setAttribute("href", fileUrl(result.folder, "jobs.csv"));
      $("open-report").setAttribute("href", fileUrl(result.folder, "report.html"));
      $("report-frame").setAttribute("src", fileUrl(result.folder, "report.html"));
    }
    $("again").textContent = failed ? "Try again" : "New search";
  }

  $("search").addEventListener("submit", startSearch);
  $("stop").addEventListener("click", function () {
    $("stop").disabled = true;
    $("stopping").hidden = false;
    api("POST", "/api/stop").catch(function () {});
  });
  $("again").addEventListener("click", function () {
    show("form-view");
    loadRuns().catch(function () {});
  });

  if (!token) {
    $("no-token").hidden = false;
    return;
  }
  Promise.all([loadBrowsers(), loadRuns()]).then(function () {
    return api("GET", "/api/status?since=0");
  }).then(function (status) {
    if (status.state === "running") {
      show("running");
      if (!polling) { polling = setInterval(poll, 1000); }
      render(status);
    } else {
      show("form-view");
    }
  }).catch(function () {});
})();
</script>
</body>
</html>
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_page.py -q`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add peerpatch_linkedin/static/index.html tests/test_page.py
git commit -m "Add the web page: form, live progress, results and past runs"
```

---

### Task 6: End-to-end through the runner and the web API

**Files:**
- Create: `tests/test_live_flow.py`

**Interfaces:**
- Consumes: `runner.run_search`, `runner.SearchOptions`, `web.App`, `browser.request_stop`, `browser.clear_stop`, `tests.web_client.WebServer`, and from `tests/test_e2e.py`: `FEED`, `OK`, `REDIRECT`, `build_posts_page`, `jobs_handler`, `read_csv`; `tests.fake_linkedin.FakeLinkedIn`

- [ ] **Step 1: Write the tests**

`tests/test_live_flow.py`:
```python
import threading

import pytest

from peerpatch_linkedin import config
from peerpatch_linkedin.browser import clear_stop, request_stop
from peerpatch_linkedin.runner import SearchOptions, run_search
from peerpatch_linkedin.web import App
from tests.fake_linkedin import FakeLinkedIn
from tests.test_e2e import FEED, OK, REDIRECT, build_posts_page, jobs_handler, read_csv
from tests.web_client import TOKEN, WebServer

JOBS_PATH = "/jobs-guest/jobs/api/seeMoreJobPostings/search"


@pytest.fixture
def linkedin(monkeypatch):
    server = FakeLinkedIn()
    settings = {"BASE_URL": server.start(), "HEADLESS": True, "WAIT_MIN_SECONDS": 0.05, "WAIT_MAX_SECONDS": 0.1,
                "RATE_LIMIT_PAUSE_SECONDS": 0.2, "LOGIN_TIMEOUT_SECONDS": 30.0}
    for name, value in settings.items():
        monkeypatch.setattr(config, name, value)
    clear_stop()
    yield server
    clear_stop()
    server.stop()


def options(tmp_path):
    return SearchOptions(job="data analyst", location="Bengaluru", results_dir=tmp_path / "results",
                         profile_base=tmp_path)


def run_in_thread(search, say=lambda line: None, stage=lambda name: None):
    """Playwright's sync API is per thread, and the test's own browser fixture holds this one."""
    box = {}
    worker = threading.Thread(target=lambda: box.update(outcome=run_search(search, say, stage)))
    worker.start()
    worker.join(120)
    assert not worker.is_alive(), "run_search didn't finish"
    return box["outcome"]


def test_stop_mid_scroll_saves_the_posts_found_so_far(linkedin, tmp_path, browser):
    linkedin.route("/feed/", OK(FEED))
    linkedin.route("/search/results/content/", OK(build_posts_page()))
    linkedin.route(JOBS_PATH, jobs_handler())

    def say(line):
        if line.startswith("  Posts:"):
            request_stop()

    outcome = run_in_thread(options(tmp_path), say)
    assert outcome.exit_code == 0 and outcome.out_dir is not None
    assert [p.author for p in outcome.posts] == ["Priya Sharma", "Acme Analytics"]
    assert "Post search stopped early: Stopped from the page." in outcome.notes
    assert "Jobs search didn't run because the run was stopped." in outcome.notes
    assert [r["author"] for r in read_csv(outcome.out_dir / "posts.csv")] == ["Priya Sharma", "Acme Analytics"]
    assert not any(path == JOBS_PATH for path, _ in linkedin.requests)


def test_stop_while_waiting_for_login_saves_nothing(linkedin, tmp_path, browser):
    linkedin.route("/feed/", REDIRECT("/login"))
    linkedin.route("/login", OK("<!doctype html><title>Sign in</title>"))
    stages = []

    def stage(name):
        stages.append(name)
        if name == "waiting-for-login":
            request_stop()

    outcome = run_in_thread(options(tmp_path), stage=stage)
    assert (outcome.out_dir, outcome.exit_code, outcome.error) == (None, 1, "Stopped. Nothing was collected.")
    assert stages == ["starting", "waiting-for-login"]
    assert not (tmp_path / "results").exists()


def test_full_search_through_the_web_api(linkedin, tmp_path, browser):
    linkedin.route("/feed/", OK(FEED))
    linkedin.route("/search/results/content/", OK(build_posts_page()))
    linkedin.route(JOBS_PATH, jobs_handler())
    web = WebServer(App(token=TOKEN, results_dir=tmp_path / "results", profile_base=tmp_path))
    try:
        assert web.call("POST", "/api/start", {"job": "data analyst", "location": "Bengaluru"})[0] == 202
        result = web.wait_until_done(timeout=90)["result"]
        assert result["error"] is None
        assert (result["posts"], result["jobs"]) == (4, 24)
        code, body, _ = web.call("GET", f"/results/{result['folder']}/posts.csv")
        assert code == 200
        assert body.decode("utf-8-sig").count("https://www.linkedin.com/feed/update/") == 4
        assert web.json("GET", "/api/runs")[1][0] == {"folder": result["folder"], "posts": 4, "jobs": 24}
    finally:
        web.close()
```

- [ ] **Step 2: Run them**

Run: `.venv/bin/pytest tests/test_live_flow.py -q`
Expected: 3 pass. These cover code written in Tasks 2 to 5, so there's no separate RED step. If one fails, fix the package code (superpowers:systematic-debugging), not the test, unless the test contradicts the spec.

- [ ] **Step 3: Run the whole suite**

Run: `.venv/bin/pytest -q`
Expected: all pass

- [ ] **Step 4: Commit**

```bash
git add tests/test_live_flow.py
git commit -m "Add end-to-end runs: stop mid-scroll, stop during login, full run through the web API"
```

---

### Task 7: README, launcher check, push

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update `README.md`**

Make these changes, in plain short sentences, no em dashes, straight quotes:

1. **Opening paragraph:** "This tool opens a page in your browser. Type a job title and a city, and it goes through LinkedIn for you using Chrome, Edge or Brave, whichever you have, and collects..." (keep the two bullets).
2. **Before you start:** replace "Google Chrome" with "Chrome, Edge or Brave. Every Windows PC has Edge. If you have none of them, the tool downloads its own browser the first time (about 150 MB)."
3. **Run it:** keep the Windows and Mac steps. Then replace "### Answer two questions" with "### Use the page": the terminal shows a link and the page opens by itself; leave the terminal window open, closing it stops the tool. On the page: type the job title, check the location, pick a browser if you want a different one, click Start.
4. **First time only: log in:** "A browser window opens on LinkedIn" (not Chrome), and add: "Each browser keeps its own login, so if you switch from Chrome to Edge you'll log in once more in Edge." Keep the three bullets. Change "The terminal waits up to 5 minutes" to "The page waits up to 5 minutes and shows a yellow banner while it does."
5. **Your login folder:** `browser-profiles` instead of `chrome-profile`, one folder per browser.
6. **What you get:** add "The page shows the results when the run finishes, with buttons to download the two CSV files. Past runs are listed under the form." Keep the `results` folder description.
7. **Stop button:** add a line: "Press Stop on the page to end early. What's been collected so far is saved. It can take a few seconds."
8. **Options:** say the page is the normal way and the options are for running in a terminal without the page. Examples: `bash run.command --job "data analyst" --location Pune` and `run.bat --job "product manager" --browser edge`. Table: replace the `--job` row with "`--job` | none | Run in the terminal instead of opening the page", and add rows for `--browser` (`auto` | Which browser to drive: `chrome`, `edge`, `brave` or `builtin`) and `--port` (`8765` | Port for the page; the next free one is used if it's taken). Change the `--profile-dir` row to "`--profile-dir` | the tool's folder | Where `browser-profiles` (your logins) lives".
9. **If something goes wrong:** replace "Google Chrome isn't installed" with "Edge isn't installed on this computer" (pick another browser in the dropdown), and change "Another PeerPatch Chrome window" to "Another PeerPatch window is already open". Add "The page says PeerPatch has stopped": the terminal window was closed; start it again. Add "The built-in browser won't download": check your internet connection, or install Chrome or Edge.

- [ ] **Step 2: Check the launcher from a clean copy**

Run:
```bash
rm -rf /tmp/claude-0/pp-launcher && mkdir -p /tmp/claude-0/pp-launcher && git archive --format=tar HEAD | tar -x -C /tmp/claude-0/pp-launcher
bash /tmp/claude-0/pp-launcher/run.command --help
rm -rf /tmp/claude-0/pp-launcher
```
Expected: "First run: setting things up", then help text listing `--browser` and `--port`.

- [ ] **Step 3: Run the whole suite**

Run: `.venv/bin/pytest -q`
Expected: all pass

- [ ] **Step 4: Commit and push**

```bash
git add README.md
git commit -m "README: the web page, browser choice and Stop"
git -c push.negotiate=true push
```
