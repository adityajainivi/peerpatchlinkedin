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
