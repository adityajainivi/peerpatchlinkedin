import io

from peerpatch_linkedin.cli import clamp_limits, job_and_location, make_console_safe, parse_args


def test_defaults():
    args = parse_args([])
    assert (args.job, args.location) == (None, None)
    assert (args.max_posts, args.max_jobs, args.post_hours, args.job_days) == (100, 200, 48, 7)
    assert not (args.skip_posts or args.skip_jobs or args.debug or args.no_open)


def test_limits_are_clamped_with_a_message():
    args = parse_args(["--post-hours", "500", "--max-jobs", "0"])
    messages = []
    clamp_limits(args, messages.append)
    assert args.post_hours == 168 and args.max_jobs == 1
    assert "168" in messages[0]


def test_console_that_cannot_print_rupee_gets_question_marks():
    raw = io.BytesIO()
    stream = io.TextIOWrapper(raw, encoding="cp1252")
    make_console_safe(stream)
    stream.write("₹ 6,00,000 → done")
    stream.flush()
    assert raw.getvalue() == b"? 6,00,000 ? done"

def test_browser_and_port_flags():
    args = parse_args([])
    assert (args.browser, args.port) == ("auto", 8765)
    args = parse_args(["--browser", "edge", "--port", "9000"])
    assert (args.browser, args.port) == ("edge", 9000)


def test_options_from_args_carries_every_setting(tmp_path):
    from peerpatch_linkedin.cli import options_from_args

    args = parse_args(["--job", "x", "--browser", "brave", "--max-posts", "5", "--skip-jobs",
                       "--profile-dir", str(tmp_path), "--results-dir", str(tmp_path / "r")])
    options = options_from_args(args, "x", "Pune")
    assert (options.job, options.location, options.browser, options.max_posts, options.skip_jobs) == (
        "x", "Pune", "brave", 5, True)
    assert (options.profile_base, options.results_dir) == (tmp_path, tmp_path / "r")


def test_job_and_location():
    assert job_and_location(parse_args(["--job", " data analyst "])) == ("data analyst", "India")
    assert job_and_location(parse_args(["--job", "x", "--location", " Pune "])) == ("x", "Pune")
    assert job_and_location(parse_args(["--job", "x", "--location", ""])) == ("x", "")
    assert job_and_location(parse_args([])) == ("", "India")


def test_no_job_starts_the_web_page(monkeypatch, tmp_path):
    from peerpatch_linkedin import cli

    calls = []
    monkeypatch.setattr(cli, "serve", lambda **kwargs: calls.append(kwargs) or 0)
    assert cli.main(["--no-open", "--port", "9001", "--results-dir", str(tmp_path)]) == 0
    assert calls[0]["port"] == 9001 and calls[0]["open_page"] is False and calls[0]["results_dir"] == tmp_path
