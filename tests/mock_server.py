"""
Mock HTTP server for SEO & GEO integration testing.
Serves compliant fixtures as well as failure edge-case endpoints.
"""

from __future__ import annotations

import http.server
import os
import socketserver
import threading

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURES_DIR = os.path.join(BASE_DIR, "fixtures")


class MockSEOHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        # Silence standard HTTP access logging in tests
        pass

    def do_GET(self) -> None:
        path = self.path

        if path in ("/", "/index.html"):
            valid_path = os.path.join(FIXTURES_DIR, "html", "valid.html")
            with open(valid_path, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        elif path == "/robots.txt":
            robots_path = os.path.join(FIXTURES_DIR, "public", "robots.txt")
            with open(robots_path, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        elif path == "/sitemap.xml":
            sitemap_path = os.path.join(FIXTURES_DIR, "public", "sitemap.xml")
            with open(sitemap_path, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "application/xml")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        elif path == "/bad-robots.txt":
            content = b"User-agent: GPTBot\nDisallow: /\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        elif path == "/bad-sitemap.xml":
            content = (
                b'<?xml version="1.0" encoding="UTF-8"?>\n'
                b'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                b"  <url><loc>http://localhost:3000/leaked-staging</loc></url>\n"
                b"</urlset>"
            )
            self.send_response(200)
            self.send_header("Content-Type", "application/xml")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        elif path == "/noindex-meta":
            content = (
                b'<!DOCTYPE html><html><head><meta name="robots" content="noindex"></head>'
                b"<body><h1>Noindex</h1></body></html>"
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        elif path == "/x-robots-noindex":
            content = b"OK"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("X-Robots-Tag", "noindex, nofollow")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        elif path == "/pricing":
            content = b"Pricing details"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        elif path == "/pricing/":
            # Redirect to non-trailing slash canonical
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
            self._thread.join()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"


if __name__ == "__main__":
    import sys

    port = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
    server = MockServer(port)
    print(f"Mock server running on {server.url} (Ctrl+C to stop)")
    try:
        server.server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server.")
        server.stop()
