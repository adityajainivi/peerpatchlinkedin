# PeerPatch LinkedIn scraper

This tool opens a page in your browser. Type a job title and a city, and it goes through LinkedIn for you using Chrome, Edge or Brave, whichever you have, and collects two things:

- Hiring posts from the last 2 days that mention the job ("We're hiring a data analyst, DM me").
- Job listings from the last 7 days for that job and city.

You get a spreadsheet of each and a results page with clickable links.

## Before you start

You need three things:

1. **Chrome, Edge or Brave.** Every Windows PC has Edge. If you have none of them, the tool downloads its own browser the first time (about 150 MB).
2. **Python 3.9 or newer.** Get it from [python.org/downloads](https://www.python.org/downloads/). On Windows, tick **Add python.exe to PATH** on the first screen of the installer. Macs often have it already. If not, the tool will tell you.
3. **A LinkedIn account.**

## Get the tool

On the GitHub page, click the green **Code** button, then **Download ZIP**. Unzip it somewhere easy to find, like your Downloads folder.

## Run it

**Windows:** double-click `run.bat`. If Windows shows a blue "Windows protected your PC" box, click **More info**, then **Run anyway**.

**Mac:** macOS blocks scripts downloaded from the internet, so a double-click shows "run.command Not Opened". Click **Done** (not Move to Bin), then use either way below.

- **Through Terminal (easiest).** Press Cmd+Space, type `Terminal`, press Enter. Type `bash` and a space, drag `run.command` from Finder into the Terminal window, and press Enter. Do this every time you run it.
- **Allow it once.** Open System Settings, then Privacy & Security. Scroll down to "run.command was blocked" and click **Open Anyway**, then enter your Mac password. Double-click `run.command` again and choose **Open Anyway**. After that a double-click works.

If a box asks to install "command line developer tools", click **Install**, wait for it to finish, and run the tool again. That's Apple's Python setup.

The first run sets itself up. That takes about a minute and needs internet.

### Use the page

A terminal window shows a link, and the page opens in your browser by itself. If it doesn't, copy the link from the terminal into your browser.

**Leave the terminal window open while you use the page.** Closing it stops the tool.

On the page:

1. Type the job title.
2. Check the location. It starts as India. Clear it to search anywhere.
3. Pick a browser if you want a different one from the one it chose.
4. Click **Start**.

The page shows what it's doing as it goes. **Stop** ends the search early and saves what's been collected so far. It can take a few seconds.

### First time only: log in

A browser window opens on LinkedIn. Log in there. The page shows a yellow banner and waits up to 5 minutes for you.

- **Use your LinkedIn email and password.** This browser window is separate from your normal one, so it doesn't have your saved passwords.
- **"Continue with Google" or Apple may not work here.** Google blocks sign-in from browsers that a program is controlling. If you normally sign in to LinkedIn with Google and don't know your LinkedIn password, set one first: on linkedin.com, click "Forgot password" and follow the email.
- **A bar saying the browser "is being controlled by automated test software" is normal.** That's this tool.

Your login is saved in the `browser-profiles` folder inside the tool's folder, one folder per browser, so next time you won't be asked. Each browser keeps its own login, so if you switch from Chrome to Edge you'll log in once more in Edge. The tool never sees or stores your password. To log the tool out for good, delete that folder.

After that, leave the browser window alone. It scrolls and clicks on its own, with short pauses so it doesn't hammer LinkedIn. A normal run takes 2 to 5 minutes.

## What you get

The page shows the results when the run finishes, with buttons to download the two CSV files. Past runs are listed under the form.

Everything is also saved in the `results` folder, one folder per search, named like `data-analyst_bengaluru_2026-11-15_1030`. Inside:

- `report.html` is the results page, with the posts as cards and the jobs as a table, and a search box on top.
- `posts.csv` has one row per hiring post: when it was posted, who posted it, their headline and profile link, whether the post names the job title, reactions, comments, the post link and the full text.
- `jobs.csv` has one row per job: posted date, title, company, location, salary if LinkedIn shows one, the job link and the company link.

Both CSV files open straight in Excel or Google Sheets, ₹ signs and all.

## Running without the page

The page is the normal way to use the tool. If you'd rather stay in a terminal, give it a job title and it runs there instead. Open a terminal in the tool's folder and run, for example:

```bash
bash run.command --job "data analyst" --location Pune
```

On Windows, in Command Prompt:

```
run.bat --job "product manager" --browser edge
```

| Option | Default | What it does |
|---|---|---|
| `--job` | none | Run in the terminal instead of opening the page |
| `--location` | `India` | Location for the jobs search. Use `""` for anywhere. Posts can't be filtered by location, because LinkedIn's post search doesn't allow it |
| `--browser` | `auto` | Which browser to drive: `chrome`, `edge`, `brave` or `builtin` |
| `--max-posts` | 100 | Stop after this many hiring posts |
| `--max-jobs` | 200 | Stop after this many jobs |
| `--post-hours` | 48 | How far back posts go, up to 168 (one week) |
| `--job-days` | 7 | How far back jobs go |
| `--skip-posts`, `--skip-jobs` | off | Run only one half |
| `--debug` | off | Save the raw LinkedIn pages into the results folder |
| `--no-open` | off | Don't open the page or the report |
| `--port` | `8765` | Port for the page. If it's taken, the next free one is used |
| `--profile-dir` | the tool's folder | Where `browser-profiles` (your logins) lives |
| `--results-dir` | `results` | Where results go |

## If something goes wrong

**"Edge isn't installed on this computer."** (or another browser's name) Pick another browser in the dropdown.

**"Another PeerPatch window is already open."** The tool's browser window from an earlier run is still open. Close it and try again.

**"The page says PeerPatch has stopped."** The terminal window was closed. Start the tool again and use the new link.

**"Couldn't download the built-in browser."** Check your internet connection, or install Chrome or Edge.

**"LinkedIn wants a security check."** LinkedIn sometimes asks you to prove you're a person. Do the check in the browser window and the tool carries on. If it isn't done within 5 minutes, the tool stops, saves what it has, and skips the rest of the run.

**"LinkedIn showed a login wall" or "rate-limiting".** LinkedIn has had enough for now. The tool stops instead of pushing on, so your account doesn't look worse. Whatever was collected before that is still saved, and the page says what happened. Try again in an hour or so.

**Zero posts, when you know there are some.** LinkedIn may have changed its page layout. Run it again with **Save raw pages** ticked under More options (or `--debug`), and send the `debug` folder from the results to whoever maintains this tool. It holds the raw pages, which show what changed.

## Be careful with your account

Automated collection breaks LinkedIn's User Agreement. Accounts that do a lot of it can get restricted or banned. This tool goes slowly and stops when LinkedIn pushes back, but that doesn't make it allowed. Keep it to one search a day, and use it at your own risk.

## For developers

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt
.venv/bin/pytest
```

The tests drive real Chrome against saved LinkedIn-shaped pages, a small fake LinkedIn server and the tool's own web page, so they need Chrome installed but no internet. The designs are in `docs/superpowers/specs/` and the build plans in `docs/superpowers/plans/`.

The code: `browsers.py` finds a browser, `browser.py` drives it, `posts.py` and `jobs.py` do the two searches, `runner.py` runs one search start to finish, `web.py` and `static/index.html` are the page, and `cli.py` picks page or terminal.

The part most likely to break is `peerpatch_linkedin/extract.js`, which reads LinkedIn's pages. When LinkedIn changes its markup, a `--debug` run gives you the pages to fix the selectors against. Add the new shape to `tests/linkedin_markup.py` first so the fix has a test.
