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
