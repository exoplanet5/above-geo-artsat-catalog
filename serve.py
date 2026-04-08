#!/usr/bin/env python3
"""Tiny static server for the catalog frontend.

Serves catalog/web/ at the chosen host/port and exposes the freshly built
data file at /api/orbits so app.js can fetch it without CORS friction.
"""
from __future__ import annotations

import argparse
import json
import webbrowser
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def make_handler(web_root: Path, data_path: Path):
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(web_root), **kwargs)

        def do_GET(self):  # noqa: N802
            if self.path == "/api/orbits":
                if not data_path.exists():
                    self._json({"error": f"missing {data_path}, run build.py first"},
                               HTTPStatus.NOT_FOUND)
                    return
                body = data_path.read_bytes()
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
                return
            super().do_GET()

        def _json(self, payload, status):
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt, *args):
            print(f"[serve] {self.address_string()} - {fmt % args}")

    return Handler


def main() -> int:
    project = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="Serve the artsat catalog UI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8090)
    parser.add_argument("--web-root", type=Path, default=project / "web")
    parser.add_argument("--data", type=Path, default=project / "data" / "orbits.json")
    parser.add_argument("--open", action="store_true", help="Open the UI in a browser")
    args = parser.parse_args()

    web_root = args.web_root.resolve()
    data = args.data.resolve()
    handler_cls = make_handler(web_root, data)

    server = ThreadingHTTPServer((args.host, args.port), handler_cls)
    url = f"http://{args.host}:{args.port}/"
    print(f"catalog server: {url}")
    print(f"web root      : {web_root}")
    print(f"data file     : {data}")

    if args.open:
        webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
