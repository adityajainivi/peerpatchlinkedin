import os

import pytest

from peerpatch_linkedin.browser import classify_url, explain_launch_error, first_line


@pytest.mark.parametrize("url, kind", [
    ("https://www.linkedin.com/feed/", "ok"),
    ("https://www.linkedin.com/search/results/content/?keywords=login", "ok"),
    ("https://www.linkedin.com/jobs/view/signup-specialist-4101234567/", "ok"),
    ("https://www.linkedin.com/login?session_redirect=%2Ffeed%2F", "login"),
    ("https://www.linkedin.com/authwall?trk=bf", "login"),
    ("https://www.linkedin.com/uas/login", "login"),
    ("https://www.linkedin.com/signup/cold-join", "login"),
    ("https://www.linkedin.com/checkpoint/lg/login-submit", "login"),
    ("https://www.linkedin.com/checkpoint/challenge/AgFz", "challenge"),
    ("", "ok"),
])
def test_classify_url(url, kind):
    assert classify_url(url) == kind


def test_missing_chrome_is_explained(tmp_path):
    msg = explain_launch_error("Chromium distribution 'chrome' is not found at /opt/google/chrome/chrome", tmp_path)
    assert "https://www.google.com/chrome/" in msg


def test_profile_in_use_is_explained(tmp_path):
    os.symlink("somehost-1234", tmp_path / "SingletonLock")  # dangling, the way Chrome leaves it
    msg = explain_launch_error("Target page, context or browser has been closed", tmp_path)
    assert "already open" in msg


def test_other_launch_errors_keep_their_first_line(tmp_path):
    assert explain_launch_error("boom\n  at stack", tmp_path) == "Chrome wouldn't start: boom"


def test_first_line():
    assert first_line(RuntimeError("one\ntwo")) == "one"
    assert first_line(RuntimeError("")) == "unknown error"


def test_open_url_reports_http_errors_that_have_empty_bodies(page):
    from peerpatch_linkedin.browser import open_url
    from tests.fake_linkedin import FakeLinkedIn

    fake = FakeLinkedIn()
    fake.route("/ok", lambda q: (200, "<p>fine</p>", {}))
    fake.route("/busy", lambda q: (429, "", {}))
    fake.route("/refused", lambda q: (999, "", {}))
    base = fake.start()
    try:
        assert open_url(page, f"{base}/ok") == 200
        assert open_url(page, f"{base}/busy") == 429
        assert open_url(page, f"{base}/refused") == 999
    finally:
        fake.stop()
