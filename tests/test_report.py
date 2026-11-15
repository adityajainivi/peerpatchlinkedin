import csv
import io
from datetime import datetime, timedelta, timezone

from peerpatch_linkedin.jobs import to_job
from peerpatch_linkedin.posts import Post
from peerpatch_linkedin.report import (
    POST_COLUMNS, excel_safe, post_row, render_report, results_dir, write_csv, write_results,
)

NOW = datetime(2026, 11, 15, 12, 0, tzinfo=timezone.utc)


def make_post(**changes):
    values = dict(urn="urn:li:activity:7000000000000000001", posted_at=NOW - timedelta(hours=5),
                  author="Priya Sharma", author_headline="Recruiter", author_url="https://www.linkedin.com/in/priya",
                  text="We're hiring", reactions=3, comments=1, mentions_title=True)
    values.update(changes)
    return Post(**values)


def render(**changes):
    args = dict(job="data analyst", location="Bengaluru", run_at=NOW, post_hours=48, job_days=7,
                posts=[], jobs=[], now=NOW, notes=[])
    args.update(changes)
    return render_report(**args)


def test_results_dir_name_and_same_minute_rerun(tmp_path):
    when = datetime(2026, 11, 15, 10, 30)
    first = results_dir(tmp_path, "Data Analyst", "Bengaluru", when)
    assert first.name == "data-analyst_bengaluru_2026-11-15_1030"
    first.mkdir()
    assert results_dir(tmp_path, "Data Analyst", "Bengaluru", when).name == "data-analyst_bengaluru_2026-11-15_1030-2"


def test_results_dir_for_titles_without_latin_letters(tmp_path):
    assert results_dir(tmp_path, "डेटा विश्लेषक", "", datetime(2026, 11, 15, 10, 30)).name == "search_2026-11-15_1030"


def test_csv_has_bom_and_keeps_rupee_and_line_breaks(tmp_path):
    path = tmp_path / "posts.csv"
    write_csv(path, POST_COLUMNS, [post_row(make_post(text="Line one\nCTC ₹12 LPA"), NOW)])
    data = path.read_bytes()
    assert data.startswith(b"\xef\xbb\xbf")
    row = next(csv.DictReader(io.StringIO(data.decode("utf-8-sig"))))
    assert row["text"] == "Line one\nCTC ₹12 LPA"
    assert row["hours_ago"] == "5.0"
    assert row["mentions_title"] == "yes"
    assert row["post_url"] == "https://www.linkedin.com/feed/update/urn:li:activity:7000000000000000001/"


def test_excel_formulas_are_neutralised():
    assert excel_safe('=HYPERLINK("http://x")') == '\'=HYPERLINK("http://x")'
    assert excel_safe("+91 98765 43210") == "'+91 98765 43210"
    assert excel_safe("@channel") == "'@channel"
    assert excel_safe("-2+3") == "'-2+3"
    assert excel_safe("- 2+3") == "'- 2+3"
    assert excel_safe("- 0+WEBSERVICE(1)") == "'- 0+WEBSERVICE(1)"
    assert excel_safe("- bullet point") == "'- bullet point"
    assert excel_safe("-5") == "-5"
    assert excel_safe("-0.1") == "-0.1"
    assert excel_safe(52) == "52"
    assert excel_safe(None) == ""


def test_report_escapes_text_and_drops_unsafe_links():
    job = to_job({"job_id": "1", "title": "Analyst <b>", "company": "Acme",
                  "company_url": "https://in.linkedin.com/company/acme"})
    page = render(posts=[make_post(text="<script>alert(1)</script> hiring", author_url="javascript:alert(1)")],
                  jobs=[job], notes=["Post search stopped early: test"])
    assert "<script>alert(1)" not in page
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page
    assert "javascript:" not in page
    assert "Analyst &lt;b&gt;" in page
    assert "Hiring posts (1)" in page and "Jobs (1)" in page
    assert "Post search stopped early: test" in page
    assert 'href="https://www.linkedin.com/jobs/view/1/"' in page


def test_long_posts_fold_behind_more_and_empty_sections_say_so():
    page = render(posts=[make_post(text="word " * 200)])
    assert "<details><summary>more</summary>" in page
    assert "No jobs found." in render()
    assert "No hiring posts found." in render()


def test_write_results_creates_three_files(tmp_path):
    report = write_results(tmp_path / "out", job="data analyst", location="", run_at=NOW, post_hours=48,
                           job_days=7, posts=[make_post()], jobs=[], now=NOW, notes=[])
    assert report.name == "report.html"
    assert sorted(p.name for p in (tmp_path / "out").iterdir()) == ["jobs.csv", "posts.csv", "report.html"]
