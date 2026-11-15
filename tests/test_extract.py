from datetime import datetime, timezone

from peerpatch_linkedin.browser import run_extract
from tests.linkedin_markup import (
    job_card, job_card_anchor, post_link_only, post_minimal, post_standard, search_page, urn_for,
)

WHEN = datetime(2026, 11, 14, 9, 30, tzinfo=timezone.utc)


def test_reads_all_three_post_shapes(page):
    a, b, c = urn_for(WHEN, salt=1), urn_for(WHEN, "ugcPost", salt=2), urn_for(WHEN, salt=3)
    page.set_content(search_page([
        post_standard(a, "Priya Sharma", "Talent Acquisition at Acme", "https://www.linkedin.com/in/priya-sharma-123",
                      "1d", "We're hiring a Data Analyst!\nDM me.", 1204, 14),
        post_minimal(b, "Acme Analytics", "https://www.linkedin.com/company/acme-analytics/",
                     "Openings for analysts. Apply now.", 52),
        post_link_only(c, "Karan Mehta", "https://www.linkedin.com/in/karan", "Hiring: Data Analyst intern."),
    ], batch=10))

    posts = {p["urn"]: p for p in run_extract(page, "peerpatchExtractPosts")}

    assert set(posts) == {a, b, c}  # the comment inside post `a` is not a post
    assert posts[a] == {
        "urn": a, "author": "Priya Sharma", "author_headline": "Talent Acquisition at Acme",
        "author_url": "https://www.linkedin.com/in/priya-sharma-123", "time_label": "1d •",
        "text": "We're hiring a Data Analyst!\nDM me.", "reactions": 1204, "comments": 14,
    }
    assert posts[b]["author"] == "Acme Analytics"
    assert posts[b]["author_url"] == "https://www.linkedin.com/company/acme-analytics/"
    assert posts[b]["text"] == "Openings for analysts. Apply now."
    assert (posts[b]["reactions"], posts[b]["comments"]) == (52, 0)
    assert posts[c]["author"] == "Karan Mehta"
    assert posts[c]["text"] == "Hiring: Data Analyst intern."


def test_empty_results_page_gives_no_posts(page):
    page.set_content(search_page([]))
    assert run_extract(page, "peerpatchExtractPosts") == []


def test_reads_both_job_card_shapes_and_skips_duplicates(page):
    page.set_content("".join([
        job_card("4101234567", "Data Analyst", "Acme Analytics", "acme-analytics", "Bengaluru, Karnataka, India",
                 "2026-11-14", "1 day ago", salary="₹6,00,000.00 - ₹9,00,000.00", benefit="Actively Hiring"),
        job_card_anchor("4107654321", "Junior Data Analyst", "Zeta Labs", "Pune, Maharashtra, India",
                        "2026-11-10", "5 days ago"),
        job_card("4101234567", "Data Analyst", "Acme Analytics", "acme-analytics", "Bengaluru, Karnataka, India",
                 "2026-11-14", "1 day ago"),
    ]))

    assert run_extract(page, "peerpatchExtractJobs") == [
        {"job_id": "4101234567", "title": "Data Analyst", "company": "Acme Analytics",
         "company_url": "https://in.linkedin.com/company/acme-analytics", "location": "Bengaluru, Karnataka, India",
         "posted_date": "2026-11-14", "posted_label": "1 day ago", "salary": "₹6,00,000.00 - ₹9,00,000.00",
         "benefit": "Actively Hiring"},
        {"job_id": "4107654321", "title": "Junior Data Analyst", "company": "Zeta Labs", "company_url": "",
         "location": "Pune, Maharashtra, India", "posted_date": "2026-11-10", "posted_label": "5 days ago",
         "salary": "", "benefit": ""},
    ]


def test_empty_jobs_page_gives_no_jobs(page):
    page.set_content("")
    assert run_extract(page, "peerpatchExtractJobs") == []
