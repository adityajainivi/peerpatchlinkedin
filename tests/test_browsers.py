import sys

import pytest

from peerpatch_linkedin.browsers import (
    BrowserDownloadFailed, BrowserInfo, BrowserNotFound, candidate_paths, choose_browser, default_browser,
    find_browsers, install_builtin, launch_options, profile_dir_for,
)

WIN_ENV = {"PROGRAMFILES": r"C:\Program Files", "PROGRAMFILES(X86)": r"C:\Program Files (x86)",
           "LOCALAPPDATA": r"C:\Users\asha\AppData\Local"}


def only(*paths):
    present = set(paths)
    return lambda path: path in present


def summary(browsers):
    return [(b.key, b.installed) for b in browsers]


def test_windows_with_only_edge_defaults_to_edge():
    edge = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
    browsers = find_browsers(platform="win32", env=WIN_ENV, home="", exists=only(edge), builtin_path="/nope")
    assert summary(browsers) == [("edge", True), ("builtin", False)]
    assert default_browser(browsers).key == "edge"
    assert launch_options(browsers[0]) == {"executable_path": edge}


def test_mac_prefers_chrome_and_finds_it_under_home_applications():
    chrome = "/Users/asha/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    brave = "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"
    browsers = find_browsers(platform="darwin", env={}, home="/Users/asha", exists=only(chrome, brave),
                             builtin_path="/nope")
    assert summary(browsers) == [("chrome", True), ("brave", True), ("builtin", False)]
    assert default_browser(browsers).path == chrome


def test_linux_with_only_brave():
    browsers = find_browsers(platform="linux", env={}, home="/home/a", exists=only("/usr/bin/brave-browser"),
                             builtin_path="/nope")
    assert default_browser(browsers).key == "brave"


def test_nothing_installed_falls_back_to_the_builtin_browser():
    browsers = find_browsers(platform="darwin", env={}, home="/Users/a", exists=only("/pw/chrome"),
                             builtin_path="/pw/chrome")
    assert summary(browsers) == [("builtin", True)]
    assert default_browser(browsers).key == "builtin"
    assert launch_options(browsers[0]) == {}


def test_windows_paths_skip_missing_environment_variables():
    assert candidate_paths("chrome", "win32", {"LOCALAPPDATA": r"C:\L"}, "") == [
        r"C:\L\Google\Chrome\Application\chrome.exe"]


def test_choose_browser():
    browsers = [BrowserInfo("edge", "Edge", "e.exe", True), BrowserInfo("builtin", "Built-in browser", None, False)]
    assert choose_browser("auto", browsers).key == "edge"
    assert choose_browser("BUILTIN", browsers).key == "builtin"
    with pytest.raises(BrowserNotFound, match="Chrome isn't installed on this computer"):
        choose_browser("chrome", browsers)
    with pytest.raises(BrowserNotFound, match="Unknown browser"):
        choose_browser("safari", browsers)


def test_old_chrome_login_folder_moves_once(tmp_path):
    (tmp_path / "chrome-profile" / "Default").mkdir(parents=True)
    target = profile_dir_for(tmp_path, "chrome")
    assert target == tmp_path / "browser-profiles" / "chrome"
    assert (target / "Default").is_dir()
    assert not (tmp_path / "chrome-profile").exists()
    assert profile_dir_for(tmp_path, "edge") == tmp_path / "browser-profiles" / "edge"


def test_old_login_folder_is_left_alone_when_the_new_one_exists(tmp_path):
    (tmp_path / "chrome-profile").mkdir()
    (tmp_path / "browser-profiles" / "chrome").mkdir(parents=True)
    profile_dir_for(tmp_path, "chrome")
    assert (tmp_path / "chrome-profile").exists()


def test_install_builtin_streams_output_and_reports_failure():
    lines = []
    install_builtin(lines.append, command=[sys.executable, "-c", "print('Downloading Chromium'); print('50%\\r100%')"])
    assert lines == ["  Downloading Chromium", "  50%", "  100%"]
    with pytest.raises(BrowserDownloadFailed, match="Check your internet connection"):
        install_builtin(lines.append, command=[sys.executable, "-c", "import sys; sys.exit(3)"])
