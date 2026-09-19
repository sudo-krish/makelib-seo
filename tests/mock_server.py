"""
Mock HTTP server for SEO & GEO integration testing.
Serves compliant fixtures as well as failure edge-case endpoints.
"""

from __future__ import annotations

import http.server
import os
import socketserver
import sys
import threading
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURES_DIR = os.path.join(BASE_DIR, "fixtures")


class MockSEOHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        # Silence standard HTTP access logging in tests
        pass

    def _read_fixture(self, subpath: str) -> bytes:
        file_path = os.path.join(FIXTURES_DIR, subpath)
        with open(file_path, "rb") as f:
            return f.read()

    def _get_static_route(self, path: str) -> tuple[int, dict[str, str], bytes] | None:
        if path in ("/", "/index.html"):
            return (
                200,
                {"Content-Type": "text/html; charset=utf-8"},
                self._read_fixture("html/valid.html"),
            )
        if path == "/robots.txt":
            return (
                200,
                {"Content-Type": "text/plain"},
                self._read_fixture("public/robots.txt"),
            )
        if path == "/sitemap.xml":
            return (
                200,
                {"Content-Type": "application/xml"},
                self._read_fixture("public/sitemap.xml"),
            )
        if path == "/bad-robots.txt":
            return (
                200,
                {"Content-Type": "text/plain"},
                b"User-agent: GPTBot\nDisallow: /\n",
            )
        if path == "/bad-sitemap.xml":
            xml = (
                b'<?xml version="1.0" encoding="UTF-8"?>\n'
                b'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                b"  <url><loc>http://localhost:3000/leaked-staging</loc></url>\n"
                b"</urlset>"
            )
            return 200, {"Content-Type": "application/xml"}, xml
        if path == "/noindex-meta":
            html = (
                b'<!DOCTYPE html><html><head><meta name="robots" '
                b'content="noindex"></head><body><h1>Noindex</h1></body></html>'
            )
            return 200, {"Content-Type": "text/html"}, html
        if path == "/x-robots-noindex":
            return (
                200,
                {
                    "Content-Type": "text/html",
                    "X-Robots-Tag": "noindex, nofollow",
                },
                b"OK",
            )
        if path == "/pricing":
            return 200, {"Content-Type": "text/html"}, b"Pricing details"
        return None

    def do_GET(self) -> None:
        path = self.path
        route = self._get_static_route(path)
        if route:
            status, headers, content = route
            self.send_response(status)
            for k, v in headers.items():
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return

        if path == "/pricing/":
            self.send_response(301)
            self.send_header("Location", "/pricing")
            self.end_headers()
        elif path.startswith("/http-to-https"):
            self.send_response(301)
            self.send_header("Location", "https://example.com" + path)
            self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()


class MockServer:
    def __init__(self, port: int = 0) -> None:
        self.server = socketserver.TCPServer(("127.0.0.1", port), MockSEOHandler)
        self.port: int = self.server.server_address[1]
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        if self._thread:
            self._thread.join(timeout=2)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"


def run_standalone(port: int = 3000) -> None:
    server = MockServer(port)
    server.start()
    print(f"Mock SEO Server running on http://127.0.0.1:{port}")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        server.stop()
        print("Server stopped.")


if __name__ == "__main__":
    port_arg = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
    run_standalone(port_arg)
