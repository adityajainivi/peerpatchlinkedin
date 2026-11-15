import io

from peerpatch_linkedin.cli import clamp_limits, make_console_safe, parse_args, resolve_search


def test_defaults():
    args = parse_args([])
    assert (args.job, args.location) == (None, None)
    assert (args.max_posts, args.max_jobs, args.post_hours, args.job_days) == (100, 200, 48, 7)
    assert not (args.skip_posts or args.skip_jobs or args.debug or args.no_open)


def test_job_flag_means_no_questions_and_india_by_default():
    asked = []
    assert resolve_search(parse_args(["--job", " data analyst "]), lambda q: asked.append(q) or "x") == ("data analyst", "India")
    assert asked == []


def test_asks_until_a_job_is_typed_then_defaults_location():
    answers = iter(["", "   ", "data analyst", ""])
    assert resolve_search(parse_args([]), lambda q: next(answers)) == ("data analyst", "India")


def test_typed_location_is_kept():
    answers = iter(["product manager", " Pune "])
    assert resolve_search(parse_args([]), lambda q: next(answers)) == ("product manager", "Pune")


def test_blank_location_flag_means_anywhere():
    assert resolve_search(parse_args(["--job", "x", "--location", ""]), input) == ("x", "")


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
