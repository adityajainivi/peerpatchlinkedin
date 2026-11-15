from datetime import datetime, timedelta, timezone

from peerpatch_linkedin import config
from peerpatch_linkedin.posts import batch_is_past_cutoff, build_search_url, select_posts, to_post
from tests.linkedin_markup import urn_for

NOW = datetime(2026, 11, 15, 12, 0, tzinfo=timezone.utc)


def raw(hours_ago, text, salt=1, **extra):
    base = {"urn": urn_for(NOW - timedelta(hours=hours_ago), salt=salt), "author": "A", "author_headline": "",
            "author_url": "", "time_label": "", "text": text, "reactions": 0, "comments": 0}
    base.update(extra)
    return base


def test_search_url_quotes_title_and_asks_for_latest_past_week(monkeypatch):
    monkeypatch.setattr(config, "BASE_URL", "https://www.linkedin.com")
    assert build_search_url("data analyst") == (
        "https://www.linkedin.com/search/results/content/?keywords=%22data%20analyst%22%20hiring"
        "&datePosted=%22past-week%22&sortBy=%22date_posted%22"
    )


def test_search_url_handles_quotes_plus_ampersand_and_hindi():
    assert "keywords=%22sales%22%20hiring" in build_search_url('  "sales" ')
    assert "keywords=%22C%2B%2B%20developer%22%20hiring" in build_search_url("C++ developer")
    assert "keywords=%22R%26D%20engineer%22%20hiring" in build_search_url("R&D engineer")
    assert "keywords=%22%E0%A4" in build_search_url("डेटा विश्लेषक")


def test_keeps_recent_hiring_posts_and_reports_every_age():
    raws = [
        raw(1, "We're hiring a data analyst", salt=1),
        raw(20, "SQL tips for data analysts", salt=2),
        raw(30, "I'm looking for a new role. #opentowork", salt=3),
        raw(47.9, "Hiring now, DM me", salt=4),
        raw(50, "Hiring now", salt=5),
    ]
    kept, ages = select_posts(raws, "data analyst", NOW, 48)
    assert [round(p.hours_ago(NOW), 1) for p in kept] == [1.0, 47.9]
    assert [p.mentions_title for p in kept] == [True, False]
    assert len(ages) == 5 and round(ages[raws[4]["urn"]]) == 50


def test_falls_back_to_time_label_when_id_has_no_time():
    post = to_post({"urn": "urn:li:activity:12345", "time_label": "3h • Edited", "text": "We are hiring"}, "x", NOW)
    assert post.posted_at == NOW - timedelta(hours=3)


def test_posts_without_time_or_text_are_handled_quietly():
    assert to_post({"urn": "", "time_label": "", "text": ""}, "x", NOW) is None
    kept, ages = select_posts([raw(2, "")], "x", NOW, 48)
    assert kept == [] and [round(a) for a in ages.values()] == [2]


def test_post_link_always_points_at_linkedin(monkeypatch):
    monkeypatch.setattr(config, "BASE_URL", "http://127.0.0.1:9999")
    post = to_post(raw(1, "hiring"), "x", NOW)
    assert post.url == f"https://www.linkedin.com/feed/update/{post.urn}/"


def test_one_old_post_in_a_fresh_batch_does_not_stop_the_search():
    assert not batch_is_past_cutoff({"a": 2, "b": 400, "c": 10}, {"a", "b", "c"}, 48)
    assert not batch_is_past_cutoff({"a": 2, "b": 400}, {"b"} | {"a"}, 48)


def test_a_batch_that_is_all_past_the_cutoff_stops_the_search():
    assert batch_is_past_cutoff({"x": 50, "y": 60, "old": 1}, {"x", "y"}, 48)


def test_no_new_posts_is_not_a_cutoff():
    assert not batch_is_past_cutoff({"x": 50}, set(), 48)
