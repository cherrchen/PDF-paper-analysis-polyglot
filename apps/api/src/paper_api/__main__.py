"""Stdlib reader API server: health probe + node re-translation (M6 6.6)."""

from __future__ import annotations

import argparse
import contextlib
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import TYPE_CHECKING

from paper_api import health
from paper_api.retranslate import BODY_READ_TIMEOUT_S, MAX_BODY_BYTES, handle_retranslate

if TYPE_CHECKING:
    from collections.abc import Mapping


def read_limited_body(
    handler: BaseHTTPRequestHandler,
) -> tuple[bytes | None, tuple[int, dict[str, object]] | None]:
    """Read a POST body bounded by MAX_BODY_BYTES, or return an error payload."""
    try:
        length = int(handler.headers.get("Content-Length") or "0")
    except ValueError:
        return None, (400, {"ok": False, "error": "invalid request body"})
    if length < 0:
        return None, (400, {"ok": False, "error": "invalid content-length"})
    if length > MAX_BODY_BYTES:
        return None, (413, {"ok": False, "error": "request body too large"})
    previous_timeout = handler.connection.gettimeout()
    try:
        handler.connection.settimeout(BODY_READ_TIMEOUT_S)
        raw = handler.rfile.read(length)
    except (TimeoutError, ConnectionError, OSError):
        return None, (408, {"ok": False, "error": "request body read timed out"})
    finally:
        with contextlib.suppress(OSError):
            handler.connection.settimeout(previous_timeout)
    if len(raw) != length:
        return None, (400, {"ok": False, "error": "incomplete request body"})
    return raw, None


def make_handler(workspace: Path, data_dir: Path) -> type[BaseHTTPRequestHandler]:
    class ReaderHandler(BaseHTTPRequestHandler):
        def _json(self, status: int, payload: Mapping[str, object]) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            if self.path in {"/", "/health", "/api/health"}:
                self._json(200, health())
                return
            if self.path == "/api/retranslate":
                self._json(405, {"ok": False, "error": "method not allowed"})
                return
            self.send_error(404)

        def do_POST(self) -> None:
            if self.path != "/api/retranslate":
                self.send_error(404)
                return
            raw, error = read_limited_body(self)
            if error is not None:
                try:
                    self._json(*error)
                except OSError:
                    return
                return
            if raw is None:
                return
            status, payload = handle_retranslate(
                raw,
                workspace=workspace,
                data_dir=data_dir,
            )
            self._json(status, payload)

        def do_PUT(self) -> None:
            self._method_not_allowed()

        def do_DELETE(self) -> None:
            self._method_not_allowed()

        def do_PATCH(self) -> None:
            self._method_not_allowed()

        def _method_not_allowed(self) -> None:
            if self.path == "/api/retranslate":
                self._json(405, {"ok": False, "error": "method not allowed"})
                return
            self.send_error(404)

        def log_message(self, format: str, *args: object) -> None:
            return

    return ReaderHandler


def main() -> None:
    parser = argparse.ArgumentParser(description="M6 reader API")
    parser.add_argument("--workspace", type=Path, default=Path("apps/web/.viewer-fixture"))
    parser.add_argument("--data-dir", type=Path, default=Path("apps/web/public/data"))
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    server = ThreadingHTTPServer(
        ("127.0.0.1", args.port),
        make_handler(args.workspace, args.data_dir),
    )
    print(f"api listening on http://127.0.0.1:{args.port}/health", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
