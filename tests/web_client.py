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
