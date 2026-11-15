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
