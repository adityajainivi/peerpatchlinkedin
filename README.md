# PeerPatch LinkedIn scraper

Type a job title and a city. This tool opens Google Chrome, goes through LinkedIn for you, and collects two things:

- Hiring posts from the last 2 days that mention the job ("We're hiring a data analyst, DM me").
- Job listings from the last 7 days for that job and city.

You get a spreadsheet of each and a web page with clickable links.

## Before you start

You need three things:

1. **Google Chrome.** Get it from [google.com/chrome](https://www.google.com/chrome/).
2. **Python 3.9 or newer.** Get it from [python.org/downloads](https://www.python.org/downloads/). On Windows, tick **Add python.exe to PATH** on the first screen of the installer. Macs often have it already. If not, the tool will tell you.
3. **A LinkedIn account.**

## Get the tool

On the GitHub page, click the green **Code** button, then **Download ZIP**. Unzip it somewhere easy to find, like your Documents folder.

## Run it

**Windows:** double-click `run.bat`. If Windows shows a blue "Windows protected your PC" box, click **More info**, then **Run anyway**.

**Mac:** right-click `run.command` and choose **Open**, then **Open** again. You only need the right-click the first time, because the file doesn't come from the App Store. After that a double-click works.

The first run sets itself up. That takes about a minute and needs internet.

### First time only: log in

A Chrome window opens on LinkedIn. Log in there, the normal way. The terminal waits up to 5 minutes for you.

Your login is saved in a folder called `chrome-profile` inside the tool's folder, so next time you won't be asked. The tool never sees or stores your password. To log the tool out for good, delete that folder.

### Answer two questions

```
Job title: data analyst
Location (press Enter for India): Bengaluru
```

Then leave it alone. The Chrome window scrolls and clicks on its own, with short pauses so it doesn't hammer LinkedIn. A normal run takes 2 to 5 minutes.

## What you get

Everything lands in the `results` folder, one folder per search, named like `data-analyst_bengaluru_2026-11-15_1030`. Inside:

- `report.html` opens in your browser when the run ends. It has the posts as cards and the jobs as a table, with a search box on top.
- `posts.csv` has one row per hiring post: when it was posted, who posted it, their headline and profile link, whether the post names the job title, reactions, comments, the post link and the full text.
- `jobs.csv` has one row per job: posted date, title, company, location, salary if LinkedIn shows one, the job link and the company link.

Both CSV files open straight in Excel or Google Sheets, ₹ signs and all.

## Options

You can skip the questions by typing the answers as options. Open a terminal in the tool's folder and run, for example:

```bash
bash run.command --job "data analyst" --location Pune
```

On Windows, in Command Prompt:

```
run.bat --job "product manager" --location "" --skip-posts
```

| Option | Default | What it does |
|---|---|---|
| `--job` | asked | Job title to search for |
| `--location` | `India` | Location for the jobs search. Use `""` for anywhere. Posts can't be filtered by location, because LinkedIn's post search doesn't allow it |
| `--max-posts` | 100 | Stop after this many hiring posts |
| `--max-jobs` | 200 | Stop after this many jobs |
| `--post-hours` | 48 | How far back posts go, up to 168 (one week) |
| `--job-days` | 7 | How far back jobs go |
| `--skip-posts`, `--skip-jobs` | off | Run only one half |
| `--debug` | off | Save the raw LinkedIn pages into the results folder |
| `--no-open` | off | Don't open the report at the end |
| `--profile-dir` | `chrome-profile` | Where Chrome keeps your LinkedIn login |
| `--results-dir` | `results` | Where results go |

## If something goes wrong

**"Google Chrome isn't installed."** Install Chrome and run the tool again.

**"Another PeerPatch Chrome window is already open."** You started the tool twice. Close the other Chrome window it opened and try again.

**"LinkedIn wants a security check."** LinkedIn sometimes asks you to prove you're a person. Do the check in the Chrome window. The tool waits 5 minutes, then carries on.

**"LinkedIn showed a login wall" or "rate-limiting".** LinkedIn has had enough for now. Whatever was collected before that is still saved, and the report says what happened. Try again in an hour or so.

**Zero posts, when you know there are some.** LinkedIn may have changed its page layout. Run it again with `--debug` and send the `debug` folder from the results to whoever maintains this tool. It holds the raw pages, which show what changed.

## Be careful with your account

Automated collection breaks LinkedIn's User Agreement. Accounts that do a lot of it can get restricted or banned. This tool goes slowly and stops when LinkedIn pushes back, but that doesn't make it allowed. Keep it to one search a day, and use it at your own risk.

## For developers

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt
.venv/bin/pytest
```

The tests drive real Chrome against saved LinkedIn-shaped pages and a small fake LinkedIn server, so they need Chrome installed but no internet. The design is in `docs/superpowers/specs/` and the build plan in `docs/superpowers/plans/`.

The part most likely to break is `peerpatch_linkedin/extract.js`, which reads LinkedIn's pages. When LinkedIn changes its markup, a `--debug` run gives you the pages to fix the selectors against. Add the new shape to `tests/linkedin_markup.py` first so the fix has a test.
