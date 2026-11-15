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
