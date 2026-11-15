# PeerPatch LinkedIn scraper: web page and any browser

Date: 15 November 2026
Status: draft, waiting for review
Builds on: `2026-11-15-linkedin-scraper-design.md` (everything there still holds unless this spec changes it)

## What changes and why

Two requests from the person who'll hand this tool to others:

1. **Web based.** Instead of answering questions in a terminal, people use a page in their normal browser: a form, live progress, results and downloads.
2. **Not just Chrome.** The tool has to work on a computer without Chrome.

Agreed in conversation:

- "Web based" means a **local** web page. The server runs on the person's own computer. Rejected: a hosted website (it would hold other people's LinkedIn passwords, and LinkedIn blocks cloud servers) and a browser extension.
- "Any browser" means the browser the tool drives behind the scenes is picked from whatever is installed: **Chrome, then Edge, then Brave**, and if none is found, a **built-in Chromium** the tool downloads once. The page itself opens in whatever browser the person uses, Safari and Firefox included. Rejected: driving the person's own Safari or Firefox (Safari forgets the login every run and needs a hidden setting; Firefox needs extra driver software).
- The server is built on **Python's standard library**. No new dependencies.

## How someone uses it

They double-click `run.bat` or `run.command`, exactly as now. The terminal prints:

```
PeerPatch is running. Your browser should open by itself.
If it doesn't, open this link: http://127.0.0.1:8765/?t=Xk3...
Leave this window open while you use the page. Close it to stop.
```

and the page opens in the default browser.

### The page

One page, three states.

**1. Form**

- Job title (required)
- Location (prefilled "India"; can be cleared for anywhere)
- Browser: a dropdown listing what was found, with the default selected. For example: "Chrome (installed)", "Edge (installed)", "Built-in browser (downloads once, about 150 MB)". Browsers that aren't installed don't appear, except the built-in one, which is always offered.
- "More options", collapsed by default: max posts (100), max jobs (200), post hours (48, at most 168), job days (7), skip posts, skip jobs, save raw pages (debug).
- Start button.
- Under the form: "Past runs", a list of folders in `results/`, newest first, each with its post and job counts and links to the report and the two CSVs.

**2. Running**

- A stage line in plain words. "Getting the browser ready", "Downloading the built-in browser (one time)", "A Chrome window has opened. Log in to LinkedIn there.", "Searching hiring posts", "Searching jobs", "Saving".
- The login stage is a highlighted banner, since that's where people get stuck.
- A live log: the same progress lines the terminal version prints.
- A Stop button. It behaves like Ctrl+C does today: what's been collected so far is saved.

**3. Done**

- "12 hiring posts, 84 jobs", plus any notes ("Post search stopped early: ...").
- Buttons: Download posts.csv, Download jobs.csv, Open report in new tab.
- The report itself, shown in the page in a frame (the same `report.html` the tool already writes).
- "New search" goes back to the form, with the last values filled in.

If the run fails before collecting anything (Chrome problem, no login in time), the page shows the message and a "Try again" button.

The page follows the computer's light or dark setting and works at phone width, though people will use it on a laptop.

## Picking and launching the browser

New module `browsers.py`.

**Detection** checks known install paths. Nothing is launched to detect.

| Key | Label | Paths checked |
|---|---|---|
| `chrome` | Chrome | Mac: `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`, same under `~/Applications`. Windows: `%PROGRAMFILES%`, `%PROGRAMFILES(X86)%` and `%LOCALAPPDATA%` + `\Google\Chrome\Application\chrome.exe`. Linux: `/opt/google/chrome/chrome` |
| `edge` | Edge | Mac: `/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge`, same under `~/Applications`. Windows: `%PROGRAMFILES(X86)%` and `%PROGRAMFILES%` + `\Microsoft\Edge\Application\msedge.exe`. Linux: `/opt/microsoft/msedge/msedge` |
| `brave` | Brave | Mac: `/Applications/Brave Browser.app/Contents/MacOS/Brave Browser`, same under `~/Applications`. Windows: `%PROGRAMFILES%`, `%PROGRAMFILES(X86)%` and `%LOCALAPPDATA%` + `\BraveSoftware\Brave-Browser\Application\brave.exe`. Linux: `/opt/brave.com/brave/brave`, `/usr/bin/brave-browser` |
| `builtin` | Built-in browser | Playwright's own Chromium (`playwright.chromium.executable_path`); "installed" if that file exists |

**Default:** the first installed of chrome, edge, brave; otherwise builtin.

**Launch:** chrome, edge and brave are launched by `executable_path`, using the path that was found. That also catches Chrome installed under `~/Applications`, which Playwright's `channel="chrome"` misses. builtin is launched with no path, so Playwright uses its own.

**Download:** if builtin is chosen and not installed, the tool runs `python -m playwright install chromium` and sends its output lines to the log. If that fails, the run stops with "Couldn't download the built-in browser. Check your internet connection, or install Chrome or Edge."

**Login folders:** each browser gets its own, `browser-profiles/<key>/`, because Chrome, Edge and Brave can't share one. If the old `chrome-profile/` folder exists and `browser-profiles/chrome/` doesn't, it's moved there on first start, so early testers stay logged in.

Messages that named Chrome now name the browser in use: "A Brave window has opened...", "Another PeerPatch Brave window is already open...". The "isn't installed" message only fires for an explicit `--browser` choice that isn't found: "Edge isn't installed on this computer. Pick another browser."

## The local server

New module `web.py`, using `http.server.ThreadingHTTPServer`, plus one static page `peerpatch_linkedin/static/index.html` with inline CSS and JS, no external files.

**Address:** `127.0.0.1` only, port 8765. If that port is taken, the next free port up to 8784. If all of those are taken, any free port.

**Token:** created at startup with `secrets.token_urlsafe(16)`. The launcher opens `/?t=<token>`. The page reads it from its own URL and sends it as the `X-PeerPatch-Token` header on every API call, or as `?t=` on download and report links. A request without the right token gets 403. The page itself (`/`) loads without a token but shows "Open the link from the PeerPatch terminal window" if it has none.

**Host check:** requests whose `Host` header isn't `127.0.0.1:<port>` or `localhost:<port>` get 403. That blocks other websites from reaching the server through DNS tricks.

**API:**

| Method and path | Does |
|---|---|
| `GET /` | the page |
| `GET /api/browsers` | `{"default": "edge", "browsers": [{"key", "label", "installed"}]}` |
| `POST /api/start` | body: job, location, browser, max_posts, max_jobs, post_hours, job_days, skip_posts, skip_jobs, debug. Starts a run in a background thread. 202 on start, 400 with a message if the job title is empty or a number is out of range, 409 if a run is already going |
| `GET /api/status?since=N` | `{"state": "idle" or "running" or "done", "stage", "log": [lines from index N on], "log_size", "result"}`. `result` is null until done, then `{"folder", "posts", "jobs", "notes", "error"}` |
| `POST /api/stop` | asks the running search to stop; 200 even if nothing is running |
| `GET /api/runs` | past runs: `[{"folder", "posts", "jobs"}]`, newest first, counts read from the CSVs |
| `GET /results/<folder>/<file>` | serves `report.html`, `posts.csv` or `jobs.csv` from that results folder, and nothing else. A folder name that isn't a direct child of `results/` gets 404 |

The page polls `/api/status` once a second while a run is going.

**One run at a time.** The whole run (browser, scraping, writing files) happens in one worker thread, because Playwright's sync API has to stay on the thread that started it.

## Shared run logic

New module `runner.py`. The body of today's `cli.main` (open the browser, log in, posts, jobs, notes, write results) moves into:

```python
run_search(options: SearchOptions, say: Say, stage: Callable[[str], None]) -> RunOutcome
```

- `SearchOptions` holds job, location, browser key, the limits and flags, plus the profile and results folders.
- `RunOutcome` holds `out_dir` (or None when nothing was saved), posts, jobs, notes, `error` (or None) and `exit_code`. The exit codes stay as now: 0 done, 1 stopped by LinkedIn or by the person before anything was collected, 2 setup problem.

The terminal and the server both call it. Behaviour is unchanged, including "stop the whole run when LinkedIn pushes back".

**Stopping.** `browser.py` gets a stop flag (`request_stop()`, `clear_stop()`). `pause()` and `polite_wait()` check it every 0.2 seconds and raise `Cancelled`. The scrapers treat `Cancelled` the way they treat Ctrl+C: save what's there and mark the result interrupted. The login wait uses `pause()` too, so Stop works there as well. A Stop pressed during a page load takes effect when that load finishes (30 seconds at most).

**Stages.** `run_search` calls `stage()` with one of `starting`, `downloading-browser`, `waiting-for-login`, `posts`, `jobs`, `saving`, `done`. `ensure_logged_in` gets an optional `on_wait` callback, so the runner can report `waiting-for-login` only when the login prompt actually shows.

## Command line

- No `--job` given: start the web page (new default). The terminal questions go away.
- `--job` given: run in the terminal as today, no page.
- New: `--browser {auto,chrome,edge,brave,builtin}` (default `auto`) and `--port` (default 8765).
- `--profile-dir` now means the folder that holds `browser-profiles` (default: next to the tool). Each browser's login lives in a subfolder.
- `--no-open` also stops the web mode from opening the page.

The launchers don't change. They already pass no arguments, which now means web mode.

## Errors in web mode

- Port problems: handled by trying the next ports.
- The page can't reach the server (terminal closed): the page shows "PeerPatch has stopped. Start it again from run.bat or run.command."
- An unexpected exception inside a run: the run ends with `error` set to the first line, whatever was collected is saved, and the server keeps running.

## Testing

1. **Browser detection.** Unit tests with fake path lists and environment: default order, Brave-only machine, nothing installed (builtin), the "chosen browser isn't installed" error, `~/Applications` Chrome, the old `chrome-profile/` move.
2. **Runner.** The existing end-to-end tests move to `run_search` through the CLI. They still run against the fake LinkedIn with headless Chrome, which detection finds on the build machine. Plus one test for Stop: request a stop mid-scroll, and the posts collected so far are saved.
3. **Server API.** `web.py` started on port 0 with a fake run function: start, status with `since`, stop, 409 when busy, 400 for an empty title, 403 for a missing token and for a foreign Host header, 404 for `/results/../x`, and past runs.
4. **The page.** Headless Chrome loads the page with a fake run function: fill the form, Start, see the log, see the done state with the download links. Then the same page without a token shows the "open the link" message.
5. **Full run through the web.** The real runner through the web API against the fake LinkedIn: start, poll until done, fetch `posts.csv` through `/results/`.

## Out of scope

- Driving the person's own Firefox or Safari.
- More than one search at a time.
- Reaching the page from another device.
- Accounts, passwords or anything stored on a server.
- Scheduling.
