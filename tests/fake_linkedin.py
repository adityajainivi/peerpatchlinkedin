"""A tiny local stand-in for linkedin.com. Records every request."""
from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse


class FakeLinkedIn:
    def __init__(self):
        self.routes = {}
        self.requests = []
        self._server = None

    def route(self, path, handler):
        self.routes[path] = handler

    def start(self) -> str:
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                parsed = urlparse(self.path)
                query = {k: v[0] for k, v in parse_qs(parsed.query, keep_blank_values=True).items()}
                fake.requests.append((parsed.path, query))
                handler = fake.routes.get(parsed.path)
                status, body, headers = handler(query) if handler else (404, "not found", {})
                data = body.encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                for key, value in headers.items():
                    self.send_header(key, value)
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        return f"http://127.0.0.1:{self._server.server_port}"

    def stop(self):
        self._server.shutdown()
        self._server.server_close()
