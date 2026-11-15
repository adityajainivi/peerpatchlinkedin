"""Run one search from start to finish. The terminal mode and the web page both use this."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from . import config
from .browser import (
    BrowserProblem, Cancelled, ScrapeResult, ScrapeStopped, Say, clear_stop, ensure_logged_in, first_line,
    open_browser,
)
from .browsers import (
    BrowserDownloadFailed, BrowserInfo, BrowserNotFound, choose_browser, find_browsers, install_builtin,
    profile_dir_for,
)
from .jobs import scrape_jobs
from .posts import scrape_posts
from .report import results_dir, write_results

MAX_POST_HOURS = 168
Stage = Callable[[str], None]


@dataclass
class SearchOptions:
    job: str
    location: str = "India"
    browser: str = "auto"
    max_posts: int = 100
    max_jobs: int = 200
    post_hours: int = 48
    job_days: int = 7
    skip_posts: bool = False
    skip_jobs: bool = False
    debug: bool = False
    profile_base: Path = field(default_factory=lambda: config.TOOL_DIR)
    results_dir: Path = field(default_factory=lambda: config.TOOL_DIR / "results")


@dataclass
class RunOutcome:
    out_dir: Path | None
    posts: list
    jobs: list
    notes: list
    error: str | None
    exit_code: int

    @property
    def report(self) -> Path | None:
        return self.out_dir / "report.html" if self.out_dir else None


def validate(options: SearchOptions) -> str | None:
    if not options.job.strip():
        return "Type a job title."
    if not 1 <= options.post_hours <= MAX_POST_HOURS:
        return f"Post hours must be 1 to {MAX_POST_HOURS}."
    if options.job_days < 1:
        return "Job days must be at least 1."
    if options.max_posts < 1 or options.max_jobs < 1:
        return "Max posts and max jobs must be at least 1."
    return None


def _failed(error: str, exit_code: int) -> RunOutcome:
    return RunOutcome(None, [], [], [], error, exit_code)


def run_search(options: SearchOptions, say: Say, stage: Stage = lambda name: None,
               browsers: list[BrowserInfo] | None = None) -> RunOutcome:
    problem = validate(options)
    if problem:
        return _failed(problem, 2)
    clear_stop()
    stage("starting")
    job, location = options.job.strip(), options.location.strip()
    now = datetime.now(timezone.utc)
    out_dir = results_dir(options.results_dir, job, location, now.astimezone())
    debug_dir = out_dir / "debug" if options.debug else None
    posts, jobs, notes = ScrapeResult(), ScrapeResult(), []
    error = None
    try:
        info = choose_browser(options.browser, find_browsers() if browsers is None else browsers)
        if info.key == "builtin" and not info.installed:
            stage("downloading-browser")
            say("Downloading the built-in browser. This happens once and can take a few minutes...")
            install_builtin(say)
        say(f"Searching LinkedIn for: {job} ({location or 'anywhere'}), using {info.label}")
        with open_browser(info, profile_dir_for(options.profile_base, info.key)) as page:
            ensure_logged_in(page, say, label=info.label, on_wait=lambda: stage("waiting-for-login"))
            if not options.skip_posts:
                stage("posts")
                say(f"Hiring posts from the last {options.post_hours} hours...")
                posts = scrape_posts(page, job, say=say, max_hours=options.post_hours, max_posts=options.max_posts,
                                     debug_dir=debug_dir, now=now)
            if not options.skip_jobs and not posts.interrupted and not posts.blocked:
                stage("jobs")
                say(f"Jobs from the last {options.job_days} days...")
                jobs = scrape_jobs(page, job, location, say=say, days=options.job_days, max_jobs=options.max_jobs,
                                   debug_dir=debug_dir)
    except (BrowserNotFound, BrowserDownloadFailed, BrowserProblem) as err:
        return _failed(str(err), 2)
    except ScrapeStopped as stop:
        return _failed(str(stop), 1)
    except (KeyboardInterrupt, Cancelled):
        if not (posts.items or jobs.items):
            return _failed("Stopped. Nothing was collected.", 1)
        notes.append("Stopped before the end.")
    except Exception as err:  # a bug or a crashed browser: keep whatever was collected
        error = f"Something went wrong: {first_line(err)}"
        if not (posts.items or jobs.items):
            return _failed(error, 1)
        notes.append(error)

    if posts.stopped:
        notes.append(f"Post search stopped early: {posts.stopped}")
    if jobs.stopped:
        notes.append(f"Jobs search stopped early: {jobs.stopped}")
    if options.skip_posts:
        notes.append("Post search was skipped.")
    if options.skip_jobs:
        notes.append("Jobs search was skipped.")
    elif posts.interrupted:
        notes.append("Jobs search didn't run because the run was stopped.")
    elif posts.blocked:
        notes.append("Jobs search didn't run because LinkedIn pushed back. Try again in an hour or so.")

    stage("saving")
    write_results(out_dir, job=job, location=location, run_at=now, post_hours=options.post_hours,
                  job_days=options.job_days, posts=posts.items, jobs=jobs.items, now=now, notes=notes)
    return RunOutcome(out_dir, posts.items, jobs.items, notes, error, 0)
