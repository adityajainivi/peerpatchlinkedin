from peerpatch_linkedin.browsers import BrowserInfo
from peerpatch_linkedin.runner import SearchOptions, run_search, validate


def test_validate():
    assert validate(SearchOptions(job="  ")) == "Type a job title."
    assert validate(SearchOptions(job="x", post_hours=169)) == "Post hours must be 1 to 168."
    assert validate(SearchOptions(job="x", job_days=0)) == "Job days must be at least 1."
    assert validate(SearchOptions(job="x", max_jobs=0)) == "Max posts and max jobs must be at least 1."
    assert validate(SearchOptions(job="x")) is None


def test_invalid_options_never_open_a_browser(tmp_path):
    outcome = run_search(SearchOptions(job="", results_dir=tmp_path), say=lambda m: None)
    assert (outcome.out_dir, outcome.exit_code, outcome.error) == (None, 2, "Type a job title.")


def test_a_missing_browser_is_a_setup_problem(tmp_path):
    stages = []
    outcome = run_search(
        SearchOptions(job="x", browser="chrome", results_dir=tmp_path / "results", profile_base=tmp_path),
        say=lambda m: None, stage=stages.append,
        browsers=[BrowserInfo("builtin", "Built-in browser", None, True)],
    )
    assert (outcome.out_dir, outcome.exit_code) == (None, 2)
    assert outcome.error == "Chrome isn't installed on this computer. Pick another browser."
    assert stages == ["starting"]
    assert list(tmp_path.iterdir()) == []
