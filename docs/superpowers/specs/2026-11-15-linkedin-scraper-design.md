# PeerPatch LinkedIn scraper: design

Date: 15 November 2026
Status: draft, waiting for review

## What it's for

Someone types a job title ("data analyst") and a location ("Bengaluru"). The tool opens their own Google Chrome, logged into their own LinkedIn account, and collects two things:

1. Hiring posts from the last 48 hours that mention that job.
2. Job listings from the last 7 days for that job and location.

It saves both as CSV files and one HTML page with clickable links.

The people running it are not developers. They're on Windows or Mac, they have Google Chrome and a LinkedIn account, and they may or may not have Python. Setup has to survive that.

## Decisions already made

- Built in Python with Playwright, driving the installed Google Chrome (`channel="chrome"`), not a bundled Chromium.
- Chrome runs with its own profile folder, `chrome-profile/`, next to the tool. The person logs into LinkedIn by hand in that window once. The tool never asks for, sees or stores a password.
- Hiring posts only. Posts by people looking for work are dropped.
- Output is two CSVs plus an HTML report.
- Code lives in its own GitHub repo, `peerpatchlinkedin`.

Rejected: attaching to the person's everyday Chrome (Chrome 136+ blocks automation on the default profile, so it needs relaunching with flags every time) and a Chrome extension (worse install story, harder to test).

## How someone runs it

Double-click `run.bat` (Windows) or `run.command` (Mac). On the first run the script creates a private Python environment in `.venv/` and installs Playwright. No browser download is needed because it uses the Chrome they already have.

Then it asks two questions in the terminal:

```
Job title: data analyst
Location (press Enter for India): Bengaluru
```

The same thing from the command line:

```
python -m peerpatch_linkedin --job "data analyst" --location "Bengaluru"
```

Options:

| Flag | Default | What it does |
|---|---|---|
| `--job` | asked | Job title to search for |
| `--location` | `India` | Location for the jobs search. Posts are not filtered by location, because LinkedIn post search can't do that |
| `--max-posts` | 100 | Stop after this many kept posts |
| `--max-jobs` | 200 | Stop after this many jobs |
| `--post-hours` | 48 | How far back posts go. 168 at most, since LinkedIn's widest useful post filter is one week |
| `--job-days` | 7 | How far back jobs go |
| `--skip-posts`, `--skip-jobs` | off | Run only one half |
| `--debug` | off | Save every page's raw HTML into the results folder |
| `--no-open` | off | Don't open the HTML report at the end |

## Flow

1. **Launch.** Start Chrome with `launch_persistent_context("chrome-profile", channel="chrome", headless=False)`. The window stays visible the whole time.
2. **Login check.** Go to `linkedin.com/feed/`. If LinkedIn redirects to a login, authwall or checkpoint page, print "Log in to LinkedIn in the Chrome window, then come back here" and poll every 2 seconds for up to 5 minutes until the feed loads. Timeout means exit with a message, and nothing is saved.
3. **Posts** (unless `--skip-posts`). See below.
4. **Jobs** (unless `--skip-jobs`). See below.
5. **Write output** and open the report.

If anything stops the run partway (Ctrl+C, a security check, a rate limit), the tool still writes whatever it collected, and the terminal says why it stopped.

## Posts: last 48 hours

LinkedIn's post search only filters by "past 24 hours", "past week" or "past month". There is no 2-day option, so the tool asks for the past week, sorted newest first, and cuts at 48 hours itself.

Search URL:

```
https://www.linkedin.com/search/results/content/?keywords="<job>" hiring&datePosted="past-week"&sortBy="date_posted"
```

The job title is in quotes so LinkedIn matches the phrase.

Scrolling: scroll to the bottom, wait 2 to 5 seconds (random), click "Show more results" if it's there, repeat. Stop when any of these happens:

- the oldest post on the page is older than the cutoff (results are newest first, so nothing further down will qualify)
- `--max-posts` kept posts reached
- two scrolls in a row load nothing new
- 40 scrolls done

**Exact post times.** Every LinkedIn post has an ID like `urn:li:activity:7392847561234567890`. The first 41 bits of that number are the creation time in milliseconds since 1970, so `posted_at = id >> 22`. That gives the real timestamp instead of a rough "2d", and it doesn't depend on LinkedIn's markup. The relative label ("1d", "23h") is still read as a fallback for any post where the ID can't be found.

**Finding posts on the page.** Each post container carries its ID in an attribute (`data-urn`, `data-chameleon-result-urn` or `data-id`). Inside it:

| Field | Main selector | Fallback |
|---|---|---|
| Author name | `.update-components-actor__title` | first link to `/in/` or `/company/` |
| Author headline | `.update-components-actor__description` | blank |
| Author link | `a.update-components-actor__meta-link` | that same `/in/` or `/company/` link |
| Text | `.update-components-text` | longest text block in the container |
| Reactions | `.social-details-social-counts__reactions-count` | number in an `aria-label` ending "reactions" |
| Comments | element whose `aria-label` ends "comments" | 0 |
| Post link | built from the ID: `https://www.linkedin.com/feed/update/<urn>/` | none needed |

Text is cleaned: "…see more" removed, whitespace collapsed. Profile links lose their tracking query strings.

**Keeping only hiring posts.** A post is kept when all three hold:

1. It's inside the time window.
2. It has hiring language. Case-insensitive patterns include: hiring, we're hiring, #hiring, opening(s), vacancy/vacancies, position open, join our team, apply now, send/share your CV or resume, DM me, referral, immediate joiner, walk-in, "looking for a/an". Rule 3 then removes the posts where the person looking is the author.
3. It doesn't read like a job seeker. Dropped if it has #opentowork, "open to work", or "I'm/I am looking for/seeking a job/role/opportunity/position".

Each kept post also gets `mentions_title` (yes/no): whether every word of the job title appears in the post. Search is fuzzy, so this lets people sort the strongest matches to the top.

Posts are deduplicated by ID.

## Jobs: last 7 days

The tool opens LinkedIn's public job listing in the same Chrome window, page by page:

```
https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords=<job>&location=<location>&f_TPR=r604800&sortBy=DD&start=<n>
```

`f_TPR=r604800` is "past 604,800 seconds", which is 7 days (`--job-days` changes the number). `sortBy=DD` is newest first. Each page returns a batch of job cards. `start` goes up by the number of cards on the page just read.

Why the public listing and not the logged-in jobs page: the public cards use plain, stable class names, while the logged-in page uses generated class names that change often.

Fields per card:

| Field | Selector |
|---|---|
| Job ID | `data-entity-urn="urn:li:jobPosting:<id>"` |
| Title | `.base-search-card__title` |
| Company | `.base-search-card__subtitle` |
| Company link | `.base-search-card__subtitle a` |
| Location | `.job-search-card__location` |
| Posted date | `time[datetime]` (date) plus its text ("2 days ago") |
| Salary | `.job-search-card__salary-info`, blank if missing |
| Benefit tag | `.job-posting-benefits__text` ("Actively Hiring"), blank if missing |
| Job link | `a.base-card__full-link`, rebuilt as `https://www.linkedin.com/jobs/view/<id>/` |

Stop when a page has no cards, a page has only jobs already seen, `--max-jobs` is reached, or 40 pages are done. Wait 2 to 5 seconds between pages.

Jobs are deduplicated by job ID and kept in the order LinkedIn returns them (newest first).

## Being careful with LinkedIn

- Visible browser, random 2 to 5 second waits, hard caps on scrolls and pages.
- **Security check or CAPTCHA** (URL contains `/checkpoint/` or a challenge page shows): pause, ask the person to solve it in the window, wait up to 5 minutes, then carry on. Otherwise stop and save.
- **Rate limit** (HTTP 429 on the jobs listing): wait 60 seconds and try once more. If that fails too, stop the jobs half and save what's there.
- **Login wall mid-run**: stop and save.
- The README states plainly that automated collection breaks LinkedIn's user agreement and can get an account restricted, and recommends one search a day at most.

## Output

```
results/
  data-analyst_bengaluru_2026-11-15_1030/
    posts.csv
    jobs.csv
    report.html
    debug/        (only with --debug)
```

**posts.csv** columns: `posted_at` (local time of the computer running it, so IST in India: `2026-11-15 09:42`), `hours_ago`, `author`, `author_headline`, `author_url`, `mentions_title`, `reactions`, `comments`, `post_url`, `text`.

**jobs.csv** columns: `posted_date`, `posted_label`, `title`, `company`, `location`, `salary`, `benefit`, `job_url`, `company_url`, `job_id`.

CSVs are UTF-8 with a byte order mark so Excel shows ₹ and non-English names properly. 
**report.html** is one self-contained file, with no internet needed to view it. It has a header with the search, run time and counts, then two sections:

- Hiring posts as cards: author and headline, how long ago, the first 300 characters of the text with the rest behind a "more" toggle, and a link to the post. Posts that name the title get a small tag.
- Jobs as a table: title (linked), company, location, posted, salary.

A search box filters both sections as you type. It follows the computer's light or dark setting.

## Code layout

```
peerpatchlinkedin/
  run.bat                 Windows launcher
  run.command             Mac launcher (also works as `bash run.command` on Linux)
  requirements.txt        playwright
  README.md               setup and use, for non-developers
  peerpatch_linkedin/
    __main__.py           python -m peerpatch_linkedin
    cli.py                read flags or ask questions, run the steps, print progress
    browser.py            launch Chrome, login check, security-check and authwall detection
    posts.py              build search URL, scroll, run extraction script, filter
    jobs.py               build listing URL, page through, run extraction script
    extract.js            in-page scripts that read posts and job cards from the DOM
    filters.py            hiring and job-seeker patterns, title match
    timeparse.py          ID to timestamp, "2d"/"23h" to hours
    report.py             CSV and HTML writers
    config.py             base URL, waits, caps
  tests/
    fixtures/             saved pages copying LinkedIn's markup
    test_*.py
```

Each file does one job. `posts.py` and `jobs.py` don't know about output. `report.py` doesn't know about browsers.

The base URL lives in `config.py` and can be overridden with the `PEERPATCH_LINKEDIN_BASE_URL` environment variable. That's only for tests, so the whole tool can run against a local fake LinkedIn.

## Launchers

`run.command` and `run.bat` both:

1. Move into the tool's folder.
2. Check that Python 3.9 or newer is there. If not, print where to get it (python.org; on Windows, tick "Add to PATH").
3. Create `.venv/` and `pip install -r requirements.txt` if `.venv/` doesn't exist yet.
4. Run `python -m peerpatch_linkedin` with any arguments passed through.
5. On Windows, `pause` at the end so the window doesn't vanish.

If Google Chrome isn't installed, Playwright's error is caught and replaced with "Install Google Chrome from google.com/chrome and run this again."

## Testing

This build machine can't reach LinkedIn, so testing happens in three layers:

1. **Unit tests** (pytest): ID-to-time decoding, relative-time parsing, hiring and job-seeker filters on real-sounding examples, title matching, URL building, CSV encoding, and HTML report escaping.
2. **Extraction tests**: Playwright loads the saved fixture pages in real Chrome from disk and runs `extract.js` against them. The fixtures copy LinkedIn's current markup, including the variants listed in the selector tables above.
3. **End-to-end run**: a small local web server plays fake LinkedIn (feed, post search with infinite scroll, job listing pages, one 429), and the full tool runs against it through `PEERPATCH_LINKEDIN_BASE_URL`. The test checks the files that come out.

The real check is the first run on a real machine against real LinkedIn. If a selector doesn't match, `--debug` saves the raw pages so they can be sent back and the selectors fixed.

## Out of scope

- Opening each job to read its full description.
- Messaging or connecting with anyone.
- Scheduling or running unattended.
- Google Sheets export.
- Filtering posts by location.
