from peerpatch_linkedin import config
from peerpatch_linkedin.jobs import build_jobs_url, status_problem, to_job


def test_jobs_url_is_past_week_newest_first(monkeypatch):
    monkeypatch.setattr(config, "BASE_URL", "https://www.linkedin.com")
    assert build_jobs_url("data analyst", "Bengaluru", 7, 0) == (
        "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
        "?keywords=data%20analyst&location=Bengaluru&f_TPR=r604800&sortBy=DD&start=0"
    )


def test_jobs_url_without_location_and_with_odd_titles():
    url = build_jobs_url('"C++ developer"', "   ", 3, 25)
    assert "location=" not in url
    assert "keywords=C%2B%2B%20developer" in url
    assert "f_TPR=r259200" in url
    assert url.endswith("start=25")
    assert "keywords=%E0%A4" in build_jobs_url("डेटा विश्लेषक", "India", 7, 0)
    assert "keywords=R%26D" in build_jobs_url("R&D", "India", 7, 0)


def test_to_job_fills_blanks_and_builds_link(monkeypatch):
    monkeypatch.setattr(config, "BASE_URL", "http://127.0.0.1:9999")
    job = to_job({"job_id": "4101234567", "title": "Data Analyst", "salary": None})
    assert job.url == "https://www.linkedin.com/jobs/view/4101234567/"
    assert (job.salary, job.company) == ("", "")


def test_status_problem():
    assert status_problem(200) is None
    assert status_problem(400) is None  # LinkedIn's "no more results"
    assert status_problem(429) == "retry"
    assert "999" in status_problem(999)
