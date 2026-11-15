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
