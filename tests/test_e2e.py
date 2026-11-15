import csv
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from tests.fake_linkedin import FakeLinkedIn
from tests.linkedin_markup import (
    job_card, job_card_anchor, post_link_only, post_minimal, post_standard, search_page, urn_for,
)

ROOT = Path(__file__).resolve().parent.parent
OK = lambda body: (lambda q: (200, body, {}))  # noqa: E731
REDIRECT = lambda to: (lambda q: (302, "", {"Location": to}))  # noqa: E731
FEED = "<!doctype html><title>Feed | LinkedIn</title><main>feed</main>"


def build_posts_page():
    now = datetime.now(timezone.utc)

    def urn(hours, salt):
        return urn_for(now - timedelta(hours=hours), salt=salt)

    std = lambda h, s, who, text: post_standard(  # noqa: E731
        urn(h, s), who, "Recruiter", f"https://www.linkedin.com/in/{who.split()[0].lower()}", f"{int(h)}h", text, 10, 2)
    cards = [
        std(1, 1, "Priya Sharma", "We're hiring a Data Analyst in Bengaluru! DM me or send your CV."),
        post_minimal(urn(5, 2), "Acme Analytics", "https://www.linkedin.com/company/acme/",
                     "Openings for analysts in Pune. Apply now."),
        std(20, 3, "Rahul Verma", "Five SQL tricks every data analyst should know."),
        std(30, 4, "Neha Gupta", "I'm looking for a new role as a Data Analyst. #OpenToWork"),
        post_link_only(urn(40, 5), "Karan Mehta", "https://www.linkedin.com/in/karan",
                       "Hiring: Data Analyst intern, Gurugram. Referrals welcome."),
        std(47, 6, "Ananya Iyer", "My team is hiring 3 data analysts. Immediate joiners preferred."),
        std(50, 7, "Old Post", "Hiring data analysts."),
        std(60, 8, "Older Post", "Hiring data analysts."),
        std(80, 9, "Oldest Post", "Hiring data analysts."),
    ]
    return search_page(cards, batch=3)


def jobs_handler():
    calls = {"rate_limited": False}
    pages = {
        "0": [job_card(f"41000000{i:02d}", f"Data Analyst {i}", "Acme", "acme", "Bengaluru, Karnataka, India",
                       "2026-11-14", "1 day ago", salary="₹6,00,000.00 - ₹9,00,000.00" if i == 1 else "",
                       benefit="Actively Hiring" if i == 2 else "") for i in range(1, 11)],
        "10": [job_card_anchor(f"41000000{i:02d}", f"Data Analyst {i}", "Zeta", "Pune, Maharashtra, India",
                               "2026-11-12", "3 days ago") for i in range(11, 21)],
        "20": [job_card(f"41000000{i:02d}", f"Data Analyst {i}", "Acme", "acme", "Remote", "2026-11-09",
                        "6 days ago") for i in (21, 22, 23, 24, 5)],  # 41000000 05 repeats
    }

    def handler(query):
        start = query.get("start", "0")
        if start == "10" and not calls["rate_limited"]:
            calls["rate_limited"] = True
            return 429, "", {}
        return 200, "".join(pages.get(start, [])), {}

    return handler


def run_tool(base_url, tmp_path, *args, **env_overrides):
    env = dict(os.environ, PEERPATCH_LINKEDIN_BASE_URL=base_url, PEERPATCH_HEADLESS="1",
               PEERPATCH_WAIT_MIN="0.05", PEERPATCH_WAIT_MAX="0.1", PEERPATCH_RATE_LIMIT_PAUSE="0.2",
               **env_overrides)
    return subprocess.run(
        [sys.executable, "-m", "peerpatch_linkedin", "--job", "data analyst", "--location", "Bengaluru",
         "--profile-dir", str(tmp_path / "profile"), "--results-dir", str(tmp_path / "results"), "--no-open", *args],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=120,
    )


def read_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


@pytest.fixture
def fake():
    server = FakeLinkedIn()
    yield server
    server.stop()


def only_results_folder(tmp_path):
    folders = list((tmp_path / "results").iterdir())
    assert len(folders) == 1
    return folders[0]


def test_full_run(fake, tmp_path, browser):
    fake.route("/feed/", OK(FEED))
    fake.route("/search/results/content/", OK(build_posts_page()))
    fake.route("/jobs-guest/jobs/api/seeMoreJobPostings/search", jobs_handler())
    run = run_tool(fake.start(), tmp_path)
    assert run.returncode == 0, run.stdout + run.stderr

    out = only_results_folder(tmp_path)
    assert out.name.startswith("data-analyst_bengaluru_")
    posts = read_csv(out / "posts.csv")
    assert [p["author"] for p in posts] == ["Priya Sharma", "Acme Analytics", "Karan Mehta", "Ananya Iyer"]
    assert [p["mentions_title"] for p in posts] == ["yes", "no", "yes", "yes"]
    assert all(p["post_url"].startswith("https://www.linkedin.com/feed/update/urn:li:") for p in posts)

    jobs = read_csv(out / "jobs.csv")
    assert len(jobs) == 24
    assert jobs[0]["salary"] == "₹6,00,000.00 - ₹9,00,000.00"
    assert jobs[1]["benefit"] == "Actively Hiring"
    assert jobs[0]["job_url"] == "https://www.linkedin.com/jobs/view/4100000001/"

    job_requests = [q for path, q in fake.requests if path.startswith("/jobs-guest/")]
    assert [q["start"] for q in job_requests] == ["0", "10", "10", "20", "25"]
    assert all(q["f_TPR"] == "r604800" and q["sortBy"] == "DD" and q["keywords"] == "data analyst"
               and q["location"] == "Bengaluru" for q in job_requests)
    post_requests = [q for path, q in fake.requests if path == "/search/results/content/"]
    assert post_requests[0] == {"keywords": '"data analyst" hiring', "datePosted": '"past-week"',
                                "sortBy": '"date_posted"'}

    report = (out / "report.html").read_text(encoding="utf-8")
    assert "Hiring posts (4)" in report and "Jobs (24)" in report
    assert "slow down" in run.stdout


def test_no_login_in_time_saves_nothing(fake, tmp_path, browser):
    fake.route("/feed/", REDIRECT("/login"))
    fake.route("/login", OK("<!doctype html><title>Sign in</title>"))
    run = run_tool(fake.start(), tmp_path, PEERPATCH_LOGIN_TIMEOUT="1")
    assert run.returncode == 1
    assert "Log in to LinkedIn in the Chrome window" in run.stdout
    assert not (tmp_path / "results").exists()


def test_login_wall_on_posts_still_collects_jobs(fake, tmp_path, browser):
    fake.route("/feed/", OK(FEED))
    fake.route("/search/results/content/", REDIRECT("/authwall"))
    fake.route("/authwall", OK("<!doctype html><title>Sign in</title>"))
    fake.route("/jobs-guest/jobs/api/seeMoreJobPostings/search", jobs_handler())
    run = run_tool(fake.start(), tmp_path)
    assert run.returncode == 0, run.stdout + run.stderr

    out = only_results_folder(tmp_path)
    assert read_csv(out / "posts.csv") == []
    assert len(read_csv(out / "jobs.csv")) == 24
    assert "Post search stopped early: LinkedIn showed a login wall" in (out / "report.html").read_text(encoding="utf-8")


def test_skip_jobs_and_debug_pages(fake, tmp_path, browser):
    fake.route("/feed/", OK(FEED))
    fake.route("/search/results/content/", OK(build_posts_page()))
    run = run_tool(fake.start(), tmp_path, "--skip-jobs", "--debug")
    assert run.returncode == 0, run.stdout + run.stderr
    out = only_results_folder(tmp_path)
    assert (out / "debug" / "posts.html").exists()
    assert read_csv(out / "jobs.csv") == []
    assert not any(path.startswith("/jobs-guest/") for path, _ in fake.requests)
