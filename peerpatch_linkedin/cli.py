"""Read flags or ask questions, run the two searches, write the results."""
from __future__ import annotations

import argparse
import sys
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from . import config
from .browser import ChromeProblem, ScrapeResult, ScrapeStopped, ensure_logged_in, open_chrome
from .jobs import scrape_jobs
from .posts import scrape_posts
from .report import results_dir, write_results

MAX_POST_HOURS = 168


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="peerpatch_linkedin",
        description="Collect LinkedIn hiring posts (last 48 hours) and job listings (last 7 days) for a job title.",
    )
    parser.add_argument("--job", help='job title to search for, e.g. "data analyst"')
    parser.add_argument("--location", help="location for the jobs search (default: India; \"\" for anywhere)")
    parser.add_argument("--max-posts", type=int, default=100, help="stop after this many hiring posts (default 100)")
    parser.add_argument("--max-jobs", type=int, default=200, help="stop after this many jobs (default 200)")
    parser.add_argument("--post-hours", type=int, default=48, help="how far back posts go, 1 to 168 (default 48)")
    parser.add_argument("--job-days", type=int, default=7, help="how far back jobs go (default 7)")
    parser.add_argument("--skip-posts", action="store_true", help="only search jobs")
    parser.add_argument("--skip-jobs", action="store_true", help="only search posts")
    parser.add_argument("--debug", action="store_true", help="save the raw pages into the results folder")
    parser.add_argument("--no-open", action="store_true", help="don't open the report when done")
    parser.add_argument("--profile-dir", type=Path, default=config.TOOL_DIR / "chrome-profile",
                        help="where Chrome keeps the LinkedIn login (default: chrome-profile next to this tool)")
    parser.add_argument("--results-dir", type=Path, default=config.TOOL_DIR / "results",
                        help="where results go (default: results next to this tool)")
    return parser.parse_args(argv)


def resolve_search(args: argparse.Namespace, ask: Callable[[str], str]) -> tuple[str, str]:
    if args.job and args.job.strip():
        location = "India" if args.location is None else args.location
        return args.job.strip(), location.strip()
    job = ""
    while not job:
        job = ask("Job title: ").strip()
    if args.location is not None:
        return job, args.location.strip()
    return job, ask("Location (press Enter for India): ").strip() or "India"


def clamp_limits(args: argparse.Namespace, say: Callable[[str], None]) -> None:
    if not 1 <= args.post_hours <= MAX_POST_HOURS:
        fixed = min(max(args.post_hours, 1), MAX_POST_HOURS)
        say(f"--post-hours must be 1 to {MAX_POST_HOURS}. Using {fixed}.")
        args.post_hours = fixed
    args.job_days = max(1, args.job_days)
    args.max_posts = max(1, args.max_posts)
    args.max_jobs = max(1, args.max_jobs)


def make_console_safe(stream=None) -> None:
    """Old Windows consoles can't print every character. Print '?' instead of crashing."""
    for s in (sys.stdout, sys.stderr) if stream is None else (stream,):
        try:
            s.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass


def say(message: str) -> None:
    print(message, flush=True)


def main(argv: list[str] | None = None, ask: Callable[[str], str] = input) -> int:
    make_console_safe()
    args = parse_args(argv)
    clamp_limits(args, say)
    try:
        job, location = resolve_search(args, ask)
    except (EOFError, KeyboardInterrupt):
        say("\nNo job title given. Nothing to do.")
        return 2

    now = datetime.now(timezone.utc)
    out_dir = results_dir(args.results_dir, job, location, now.astimezone())
    debug_dir = out_dir / "debug" if args.debug else None
    posts, jobs, notes = ScrapeResult(), ScrapeResult(), []

    say(f"Searching LinkedIn for: {job} ({location or 'anywhere'})")
    try:
        with open_chrome(args.profile_dir) as page:
            ensure_logged_in(page, say)
            if not args.skip_posts:
                say(f"Hiring posts from the last {args.post_hours} hours...")
                posts = scrape_posts(page, job, say=say, max_hours=args.post_hours, max_posts=args.max_posts,
                                     debug_dir=debug_dir, now=now)
            if not args.skip_jobs and not posts.interrupted:
                say(f"Jobs from the last {args.job_days} days...")
                jobs = scrape_jobs(page, job, location, say=say, days=args.job_days, max_jobs=args.max_jobs,
                                   debug_dir=debug_dir)
    except ChromeProblem as problem:
        say(str(problem))
        return 2
    except ScrapeStopped as stop:
        say(str(stop))
        return 1
    except KeyboardInterrupt:
        if not (posts.items or jobs.items):
            say("\nStopped. Nothing was collected.")
            return 1
        notes.append("Stopped with Ctrl+C.")

    if posts.stopped:
        notes.append(f"Post search stopped early: {posts.stopped}")
    if jobs.stopped:
        notes.append(f"Jobs search stopped early: {jobs.stopped}")
    if args.skip_posts:
        notes.append("Post search was skipped.")
    if args.skip_jobs:
        notes.append("Jobs search was skipped.")
    elif posts.interrupted:
        notes.append("Jobs search didn't run because the run was stopped.")

    report = write_results(out_dir, job=job, location=location, run_at=now, post_hours=args.post_hours,
                           job_days=args.job_days, posts=posts.items, jobs=jobs.items, now=now, notes=notes)
    for note in notes:
        say(note)
    say(f"\nDone. {len(posts.items)} hiring posts, {len(jobs.items)} jobs.")
    say(f"Saved in: {out_dir}")
    if not args.no_open:
        webbrowser.open(report.resolve().as_uri())
    return 0
