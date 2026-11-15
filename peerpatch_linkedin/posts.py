"""Hiring posts from LinkedIn post search."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote, urlencode

from playwright.sync_api import Error as PlaywrightError

from . import config
from .browser import (
    Cancelled, ScrapeResult, ScrapeStopped, Say, check_for_walls, first_line, polite_wait, run_extract, save_debug,
)
from .filters import is_hiring_post
from .filters import mentions_title as _mentions_title
from .timeparse import relative_label_to_hours, urn_to_datetime

_LOAD_MORE = "button.scaffold-finite-scroll__load-button, button:has-text('Show more results')"


@dataclass
class Post:
    urn: str
    posted_at: datetime
    author: str
    author_headline: str
    author_url: str
    text: str
    reactions: int
    comments: int
    mentions_title: bool

    @property
    def url(self) -> str:
        return f"{config.PUBLIC_URL}/feed/update/{self.urn}/"

    def hours_ago(self, now: datetime) -> float:
        return (now - self.posted_at).total_seconds() / 3600


def _clean_title(job: str) -> str:
    return (job or "").strip().strip('"“”').strip()


def build_search_url(job: str) -> str:
    params = {"keywords": f'"{_clean_title(job)}" hiring', "datePosted": '"past-week"', "sortBy": '"date_posted"'}
    return f"{config.BASE_URL}/search/results/content/?{urlencode(params, quote_via=quote)}"


def to_post(raw: dict, job: str, now: datetime) -> Post | None:
    urn = raw.get("urn") or ""
    posted = urn_to_datetime(urn)
    if posted is None:
        hours = relative_label_to_hours(raw.get("time_label") or "")
        if hours is None:
            return None
        posted = now - timedelta(hours=hours)
    text = raw.get("text") or ""
    return Post(
        urn=urn,
        posted_at=posted,
        author=raw.get("author") or "",
        author_headline=raw.get("author_headline") or "",
        author_url=raw.get("author_url") or "",
        text=text,
        reactions=int(raw.get("reactions") or 0),
        comments=int(raw.get("comments") or 0),
        mentions_title=_mentions_title(text, job),
    )


def select_posts(raws: list[dict], job: str, now: datetime, max_hours: float) -> tuple[list[Post], dict[str, float]]:
    """Keep recent hiring posts. Also return the age in hours of every post with a known time, by URN."""
    kept: list[Post] = []
    ages: dict[str, float] = {}
    for raw in raws:
        post = to_post(raw, job, now)
        if post is None:
            continue
        age = post.hours_ago(now)
        ages[post.urn] = age
        if age <= max_hours and is_hiring_post(post.text):
            kept.append(post)
    return kept, ages


def batch_is_past_cutoff(ages: dict[str, float], new_urns: set[str], max_hours: float) -> bool:
    """True when every newly loaded post with a known time is past the cutoff.

    Looking at the whole new batch, not the single oldest post, means one stray old post
    (LinkedIn's "Latest" order isn't strictly by date) doesn't end the search early.
    """
    fresh = [ages[urn] for urn in new_urns if urn in ages]
    return bool(fresh) and min(fresh) > max_hours


def _load_more(page) -> None:
    run_extract(page, "peerpatchScrollToBottom")
    try:
        page.mouse.move(600, 500)
        page.mouse.wheel(0, 4000)
        button = page.locator(_LOAD_MORE).first
        if button.is_visible():
            button.click(timeout=3000)
    except PlaywrightError:
        pass


def scrape_posts(page, job: str, *, say: Say, max_hours: float = 48, max_posts: int = 100,
                 debug_dir: Path | None = None, now: datetime | None = None) -> ScrapeResult:
    now = now or datetime.now(timezone.utc)
    kept: dict[str, Post] = {}
    seen: set[str] = set()

    def result(stopped: str | None = None, interrupted: bool = False, blocked: bool = False) -> ScrapeResult:
        posts = sorted(kept.values(), key=lambda p: p.posted_at, reverse=True)[:max_posts]
        return ScrapeResult(posts, stopped, interrupted, blocked)

    try:
        url = build_search_url(job)
        page.goto(url, wait_until="domcontentloaded")
        if check_for_walls(page, say):
            page.goto(url, wait_until="domcontentloaded")
            check_for_walls(page, say)
        polite_wait(page)
        stale_rounds = 0
        for _ in range(config.MAX_SCROLLS):
            raws = run_extract(page, "peerpatchExtractPosts")
            new_urns = {r["urn"] for r in raws} - seen
            seen |= new_urns
            posts, ages = select_posts(raws, job, now, max_hours)
            for post in posts:
                kept.setdefault(post.urn, post)
            say(f"  Posts: {len(seen)} looked at, {len(kept)} hiring posts kept")
            if len(kept) >= max_posts or batch_is_past_cutoff(ages, new_urns, max_hours):
                break
            stale_rounds = 0 if new_urns else stale_rounds + 1
            if stale_rounds >= 2:
                break
            _load_more(page)
            polite_wait(page)
            check_for_walls(page, say)
        save_debug(page, debug_dir, "posts")
    except ScrapeStopped as stop:
        save_debug(page, debug_dir, "posts-stopped")
        return result(str(stop), blocked=True)
    except PlaywrightError as err:
        return result(f"The browser had a problem during the post search: {first_line(err)}")
    except Cancelled:
        return result("Stopped from the page.", interrupted=True)
    except KeyboardInterrupt:
        return result("Stopped with Ctrl+C.", interrupted=True)
    return result()
