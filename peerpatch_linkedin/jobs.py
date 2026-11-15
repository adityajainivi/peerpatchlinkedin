"""Job listings from LinkedIn's public job search."""
from __future__ import annotations

from dataclasses import dataclass, fields
from pathlib import Path
from urllib.parse import quote, urlencode

from playwright.sync_api import Error as PlaywrightError

from . import config
from .browser import (
    Cancelled, ScrapeResult, ScrapeStopped, Say, check_for_walls, first_line, open_url, pause, polite_wait,
    run_extract, save_debug,
)


@dataclass
class Job:
    job_id: str
    title: str
    company: str
    company_url: str
    location: str
    posted_date: str
    posted_label: str
    salary: str
    benefit: str

    @property
    def url(self) -> str:
        return f"{config.PUBLIC_URL}/jobs/view/{self.job_id}/"


def build_jobs_url(job: str, location: str, days: int, start: int) -> str:
    params = {"keywords": (job or "").strip().strip('"“”').strip()}
    if (location or "").strip():
        params["location"] = location.strip()
    params.update({"f_TPR": f"r{int(days) * 86400}", "sortBy": "DD", "start": str(int(start))})
    return f"{config.BASE_URL}/jobs-guest/jobs/api/seeMoreJobPostings/search?{urlencode(params, quote_via=quote)}"


def to_job(raw: dict) -> Job:
    return Job(**{f.name: str(raw.get(f.name) or "") for f in fields(Job)})


def status_problem(status: int) -> str | None:
    if status == 429:
        return "retry"
    if status == 999:
        return "LinkedIn refused the jobs search (HTTP 999). That usually clears in a few hours."
    return None


def scrape_jobs(page, job: str, location: str, *, say: Say, days: int = 7, max_jobs: int = 200,
                debug_dir: Path | None = None) -> ScrapeResult:
    found: dict[str, Job] = {}

    def result(stopped: str | None = None, interrupted: bool = False) -> ScrapeResult:
        return ScrapeResult(list(found.values())[:max_jobs], stopped, interrupted)

    start = 0
    retried = False
    try:
        for page_number in range(1, config.MAX_JOB_PAGES + 1):
            problem = status_problem(open_url(page, build_jobs_url(job, location, days, start)))
            if problem == "retry":
                if retried:
                    return result("LinkedIn is rate-limiting the jobs search (HTTP 429). Try again in an hour.")
                retried = True
                say(f"  Jobs: LinkedIn asked us to slow down. Waiting {int(config.RATE_LIMIT_PAUSE_SECONDS)} seconds...")
                pause(page, config.RATE_LIMIT_PAUSE_SECONDS)
                continue
            if problem:
                return result(problem)
            retried = False
            if check_for_walls(page, say):
                continue  # security check solved: load the same page again
            save_debug(page, debug_dir, f"jobs-{page_number:02d}")
            raws = run_extract(page, "peerpatchExtractJobs")
            fresh = 0
            for raw in raws:
                item = to_job(raw)
                if item.job_id and item.job_id not in found:
                    found[item.job_id] = item
                    fresh += 1
            say(f"  Jobs: page {page_number}, {len(found)} found")
            if not raws or fresh == 0 or len(found) >= max_jobs:
                break
            start += len(raws)
            polite_wait(page)
    except ScrapeStopped as stop:
        return result(str(stop))
    except PlaywrightError as err:
        return result(f"The browser had a problem during the jobs search: {first_line(err)}")
    except Cancelled:
        return result("Stopped from the page.", interrupted=True)
    except KeyboardInterrupt:
        return result("Stopped with Ctrl+C.", interrupted=True)
    return result()
