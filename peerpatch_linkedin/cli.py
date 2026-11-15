"""Command line: run one search in the terminal."""
from __future__ import annotations

import argparse
import sys
import webbrowser
from pathlib import Path
from typing import Callable

from . import config
from .browsers import KEYS
from .runner import MAX_POST_HOURS, RunOutcome, SearchOptions, run_search


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="peerpatch_linkedin",
        description="Collect LinkedIn hiring posts (last 48 hours) and job listings (last 7 days) for a job title.",
    )
    parser.add_argument("--job", help='job title to search for, e.g. "data analyst"')
    parser.add_argument("--location", help="location for the jobs search (default: India; \"\" for anywhere)")
    parser.add_argument("--browser", choices=KEYS, default="auto",
                        help="browser to drive (default: Chrome, then Edge, then Brave, else the built-in one)")
    parser.add_argument("--max-posts", type=int, default=100, help="stop after this many hiring posts (default 100)")
    parser.add_argument("--max-jobs", type=int, default=200, help="stop after this many jobs (default 200)")
    parser.add_argument("--post-hours", type=int, default=48, help="how far back posts go, 1 to 168 (default 48)")
    parser.add_argument("--job-days", type=int, default=7, help="how far back jobs go (default 7)")
    parser.add_argument("--skip-posts", action="store_true", help="only search jobs")
    parser.add_argument("--skip-jobs", action="store_true", help="only search posts")
    parser.add_argument("--debug", action="store_true", help="save the raw pages into the results folder")
    parser.add_argument("--no-open", action="store_true", help="don't open the report or the page")
    parser.add_argument("--port", type=int, default=8765, help="port for the web page (default 8765)")
    parser.add_argument("--profile-dir", type=Path, default=config.TOOL_DIR,
                        help="folder that holds browser-profiles, where each browser keeps its LinkedIn login "
                             "(default: next to this tool)")
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


def options_from_args(args: argparse.Namespace, job: str, location: str) -> SearchOptions:
    return SearchOptions(
        job=job, location=location, browser=args.browser, max_posts=args.max_posts, max_jobs=args.max_jobs,
        post_hours=args.post_hours, job_days=args.job_days, skip_posts=args.skip_posts, skip_jobs=args.skip_jobs,
        debug=args.debug, profile_base=args.profile_dir, results_dir=args.results_dir,
    )


def report_outcome(outcome: RunOutcome, open_report: bool) -> int:
    if outcome.out_dir is None:
        say(outcome.error or "Nothing was saved.")
        return outcome.exit_code
    for note in outcome.notes:
        say(note)
    say(f"\nDone. {len(outcome.posts)} hiring posts, {len(outcome.jobs)} jobs.")
    say(f"Saved in: {outcome.out_dir}")
    if open_report:
        webbrowser.open(outcome.report.resolve().as_uri())
    return outcome.exit_code


def main(argv: list[str] | None = None, ask: Callable[[str], str] = input) -> int:
    make_console_safe()
    args = parse_args(argv)
    clamp_limits(args, say)
    try:
        job, location = resolve_search(args, ask)
    except (EOFError, KeyboardInterrupt):
        say("\nNo job title given. Nothing to do.")
        return 2
    outcome = run_search(options_from_args(args, job, location), say)
    return report_outcome(outcome, open_report=not args.no_open)
