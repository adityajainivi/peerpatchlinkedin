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
