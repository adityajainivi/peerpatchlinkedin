from contextlib import contextmanager

import pytest

from peerpatch_linkedin import runner
from peerpatch_linkedin.browser import clear_stop, request_stop
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


@pytest.fixture
def no_leftover_stop():
    clear_stop()
    yield
    clear_stop()


def _options(tmp_path):
    return SearchOptions(job="x", results_dir=tmp_path / "results", profile_base=tmp_path)


def _never(name):
    def fail(*args, **kwargs):
        pytest.fail(f"{name} ran after Stop")
    return fail


@pytest.mark.parametrize("finishes", [False, True], ids=["stopped-mid-download", "stopped-as-it-finished"])
def test_stop_during_the_browser_download_saves_nothing(tmp_path, monkeypatch, no_leftover_stop, finishes):
    def fake_install(say, should_stop=None):
        request_stop()
        return finishes
    monkeypatch.setattr(runner, "install_builtin", fake_install)
    monkeypatch.setattr(runner, "open_browser", _never("open_browser"))
    stages = []
    outcome = run_search(_options(tmp_path), say=lambda m: None, stage=stages.append,
                         browsers=[BrowserInfo("builtin", "Built-in browser", None, False)])
    assert (outcome.out_dir, outcome.exit_code, outcome.error) == (None, 1, "Stopped. Nothing was collected.")
    assert stages == ["starting", "downloading-browser"]


def test_stop_pressed_during_login_never_starts_scraping(tmp_path, monkeypatch, no_leftover_stop):
    @contextmanager
    def fake_open(info, profile_dir):
        yield object()
    monkeypatch.setattr(runner, "open_browser", fake_open)
    monkeypatch.setattr(runner, "ensure_logged_in", lambda page, say, **kwargs: request_stop())
    monkeypatch.setattr(runner, "scrape_posts", _never("scrape_posts"))
    outcome = run_search(_options(tmp_path), say=lambda m: None, browsers=[BrowserInfo("chrome", "Chrome", "/c", True)])
    assert (outcome.out_dir, outcome.error) == (None, "Stopped. Nothing was collected.")
    assert not (tmp_path / "results").exists()
