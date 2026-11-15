"""Write results: two CSVs and one self-contained HTML page. Knows nothing about browsers."""
from __future__ import annotations

import csv
import html
import re
from datetime import datetime
from pathlib import Path
from string import Template

POST_COLUMNS = ["posted_at", "hours_ago", "author", "author_headline", "author_url", "mentions_title",
                "reactions", "comments", "post_url", "text"]
JOB_COLUMNS = ["posted_date", "posted_label", "title", "company", "location", "salary", "benefit",
               "job_url", "company_url", "job_id"]


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")[:40].strip("-")


def results_dir(root: Path, job: str, location: str, when: datetime) -> Path:
    name = "_".join(part for part in (_slug(job), _slug(location)) if part) or "search"
    name = f"{name}_{when.strftime('%Y-%m-%d_%H%M')}"
    candidate, n = root / name, 2
    while candidate.exists():
        candidate, n = root / f"{name}-{n}", n + 1
    return candidate


def excel_safe(value) -> str:
    """Stop Excel from treating a cell as a formula."""
    text = "" if value is None else str(value)
    if text[:1] in ("=", "+", "@", "\t", "\r") or (text[:1] == "-" and text[1:2] not in ("", " ")):
        return "'" + text
    return text


def safe_url(url: str) -> str:
    return url if re.match(r"^https?://", url or "", re.IGNORECASE) else ""


def post_row(post, now: datetime) -> dict:
    return {
        "posted_at": post.posted_at.astimezone().strftime("%Y-%m-%d %H:%M"),
        "hours_ago": f"{post.hours_ago(now):.1f}",
        "author": post.author,
        "author_headline": post.author_headline,
        "author_url": post.author_url,
        "mentions_title": "yes" if post.mentions_title else "no",
        "reactions": post.reactions,
        "comments": post.comments,
        "post_url": post.url,
        "text": post.text,
    }


def job_row(job) -> dict:
    return {
        "posted_date": job.posted_date, "posted_label": job.posted_label, "title": job.title,
        "company": job.company, "location": job.location, "salary": job.salary, "benefit": job.benefit,
        "job_url": job.url, "company_url": job.company_url, "job_id": job.job_id,
    }


def write_csv(path: Path, columns: list[str], rows: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: excel_safe(row.get(key, "")) for key in columns})


def _ago(hours: float) -> str:
    if hours < 1:
        return f"{max(1, round(hours * 60))} min ago"
    if hours < 48:
        return f"{round(hours)} h ago"
    return f"{round(hours / 24)} days ago"


def _split_text(text: str, limit: int = 300) -> tuple[str, str]:
    if len(text) <= limit:
        return text, ""
    cut = text.rfind(" ", 0, limit)
    if cut < limit // 2:
        cut = limit
    return text[:cut].rstrip() + "…", text[cut:].strip()


def _link(url: str, label: str, css: str = "") -> str:
    e = html.escape
    url = safe_url(url)
    css_attr = f' class="{css}"' if css else ""
    if not url:
        return f"<span{css_attr}>{e(label)}</span>"
    return f'<a{css_attr} href="{e(url)}" target="_blank" rel="noopener">{e(label)}</a>'


def _post_card(post, now: datetime) -> str:
    e = html.escape
    first, rest = _split_text(post.text)
    more = f'<details><summary>more</summary><div class="text">{e(rest)}</div></details>' if rest else ""
    tag = '<span class="tag">names the job</span>' if post.mentions_title else ""
    words = e(" ".join([post.author, post.author_headline, post.text]).lower())
    return (
        f'<article class="post" data-filter="{words}"><header>'
        f'{_link(post.author_url, post.author or "Unknown", "author")}'
        f'<span class="headline">{e(post.author_headline)}</span>'
        f'<span class="when">{_ago(post.hours_ago(now))}</span>{tag}</header>'
        f'<div class="text">{e(first)}</div>{more}'
        f'<p class="foot">{_link(post.url, "Open post")} '
        f'<span class="when">{post.reactions} reactions, {post.comments} comments</span></p></article>'
    )


def _jobs_table(jobs) -> str:
    e = html.escape
    if not jobs:
        return '<p class="empty">No jobs found.</p>'
    rows = []
    for job in jobs:
        words = e(" ".join([job.title, job.company, job.location, job.salary]).lower())
        rows.append(
            f'<tr data-filter="{words}"><td>{_link(job.url, job.title or "Untitled")}</td>'
            f"<td>{_link(job.company_url, job.company)}</td><td>{e(job.location)}</td>"
            f"<td>{e(job.posted_label or job.posted_date)}</td><td>{e(job.salary)}</td></tr>"
        )
    return (
        '<div class="table-wrap"><table><thead><tr><th>Title</th><th>Company</th><th>Location</th>'
        "<th>Posted</th><th>Salary</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>"
    )


_PAGE = Template("""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>$title</title>
<style>
:root { --bg: #f7f6f2; --card: #ffffff; --text: #1d1d1b; --muted: #6b6a66; --line: #e2e0d9; --accent: #0a66c2; --tag: #e8f1fb; }
@media (prefers-color-scheme: dark) {
  :root { --bg: #161615; --card: #20201e; --text: #ecebe6; --muted: #a3a29c; --line: #34332f; --accent: #70b5f9; --tag: #1d2c3d; }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--text); font: 15px/1.5 -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
main { max-width: 980px; margin: 0 auto; padding: 24px 16px 64px; }
h1 { font-size: 24px; margin: 0 0 4px; }
h2 { font-size: 18px; margin: 32px 0 12px; }
.meta { color: var(--muted); margin: 0 0 16px; }
.note { background: var(--tag); border-radius: 8px; padding: 10px 12px; margin: 8px 0; }
input[type=search] { width: 100%; padding: 10px 12px; font: inherit; border: 1px solid var(--line); border-radius: 8px; background: var(--card); color: var(--text); }
.post { background: var(--card); border: 1px solid var(--line); border-radius: 10px; padding: 14px 16px; margin: 0 0 12px; }
.post header { display: flex; flex-wrap: wrap; gap: 4px 10px; align-items: baseline; }
.author { font-weight: 600; }
.headline, .when { color: var(--muted); font-size: 13px; }
.tag { background: var(--tag); color: var(--accent); border-radius: 999px; padding: 1px 8px; font-size: 12px; }
.text { white-space: pre-line; margin: 8px 0; overflow-wrap: anywhere; }
.foot { margin: 8px 0 0; }
details summary { cursor: pointer; color: var(--accent); }
a { color: var(--accent); }
.table-wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; background: var(--card); border: 1px solid var(--line); }
th, td { text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--line); vertical-align: top; }
th { font-size: 13px; color: var(--muted); font-weight: 600; }
.empty { color: var(--muted); }
</style>
</head>
<body>
<main>
<h1>$heading</h1>
<p class="meta">$meta</p>
$notes
<input type="search" id="filter" placeholder="Filter posts and jobs" aria-label="Filter posts and jobs">
<h2>Hiring posts ($post_count)</h2>
$posts
<h2>Jobs ($job_count)</h2>
$jobs
</main>
<script>
document.getElementById("filter").addEventListener("input", function (event) {
  var query = event.target.value.toLowerCase();
  document.querySelectorAll("[data-filter]").forEach(function (item) {
    item.hidden = query !== "" && item.getAttribute("data-filter").indexOf(query) === -1;
  });
});
</script>
</body>
</html>
""")


def render_report(*, job, location, run_at, post_hours, job_days, posts, jobs, now, notes) -> str:
    e = html.escape
    where = f" in {location}" if location else ""
    posts_html = "".join(_post_card(p, now) for p in posts) or '<p class="empty">No hiring posts found.</p>'
    return _PAGE.substitute(
        title=e(f"{job} jobs{where}"),
        heading=e(f"{job}{where}"),
        meta=e(f"Run {run_at.astimezone().strftime('%d %b %Y, %H:%M')}. "
               f"Posts from the last {post_hours} hours, jobs from the last {job_days} days."),
        notes="".join(f'<p class="note">{e(n)}</p>' for n in notes),
        post_count=len(posts),
        posts=posts_html,
        job_count=len(jobs),
        jobs=_jobs_table(jobs),
    )


def write_results(out_dir: Path, *, job, location, run_at, post_hours, job_days, posts, jobs, now, notes) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(out_dir / "posts.csv", POST_COLUMNS, [post_row(p, now) for p in posts])
    write_csv(out_dir / "jobs.csv", JOB_COLUMNS, [job_row(j) for j in jobs])
    report = out_dir / "report.html"
    report.write_text(
        render_report(job=job, location=location, run_at=run_at, post_hours=post_hours, job_days=job_days,
                      posts=posts, jobs=jobs, now=now, notes=notes),
        encoding="utf-8",
    )
    return report
