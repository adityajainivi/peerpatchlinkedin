from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_login_folders_are_never_committed():
    ignored = (ROOT / ".gitignore").read_text().split()
    assert "browser-profiles/" in ignored and "chrome-profile/" in ignored
