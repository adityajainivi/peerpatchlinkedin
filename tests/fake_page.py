"""Just enough of a Playwright page to test waiting and stopping without a browser."""
from types import SimpleNamespace


class FakePage:
    def __init__(self, url="http://127.0.0.1/feed/", goto_url=None, jobs=None):
        self.url = url
        self.goto_url = goto_url  # where goto() lands; None means the URL asked for
        self.jobs = jobs or []
        self.waits = []
        self.context = SimpleNamespace(cookies=lambda: [])

    def goto(self, url, wait_until=None):
        self.url = self.goto_url or url
        return SimpleNamespace(status=200)

    def wait_for_timeout(self, ms):
        self.waits.append(ms)

    def on(self, event, handler):
        pass

    def remove_listener(self, event, handler):
        pass

    def evaluate(self, script):
        return list(self.jobs)

    def content(self):
        return ""
