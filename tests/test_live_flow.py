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
