"""Stdlib reader API server: health probe, node re-translation, console surfaces."""

from __future__ import annotations

import argparse
import contextlib
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import TYPE_CHECKING

from paper_api import health
from paper_api.jobs import (
    handle_get_job,
    handle_list_jobs,
    handle_retry_job,
    handle_submit_job,
    match_jobs_path,
)
from paper_api.retranslate import BODY_READ_TIMEOUT_S, MAX_BODY_BYTES, handle_retranslate
from paper_api.status import STATUS_PATH, handle_status
from paper_api.uploads import UPLOAD_CHUNK_BYTES, UPLOAD_READ_TIMEOUT_S, UPLOADS_PATH, store_upload
from paper_api.workspaces import (
    OPEN_WORKSPACE_PATH,
    WORKSPACES_PATH,
    handle_list_workspaces,
    handle_open_workspace,
)

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping
    from io import BufferedIOBase

# Console surfaces read and write on opposite sides of the ownership line:
# listings are GET-only, while uploads and workspace opens are POST-only.
_GET_ONLY_PATHS = frozenset({STATUS_PATH, WORKSPACES_PATH})
_POST_ONLY_PATHS = frozenset({UPLOADS_PATH, OPEN_WORKSPACE_PATH})
_CONSOLE_PATHS = _GET_ONLY_PATHS | _POST_ONLY_PATHS


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


def upload_chunks(stream: BufferedIOBase, content_length: int) -> Iterator[bytes]:
    """Yield a request body in ``UPLOAD_CHUNK_BYTES`` blocks, never more than asked.

    ``rfile.read(n)`` blocks until ``n`` bytes or EOF, so a keep-alive client
    that sends exactly its declared length would otherwise stall the socket
    into the read timeout: the declared length, not EOF, ends this stream.
    A short read ends it too, and ``store_upload`` then reports the count it
    actually received.
    """
    remaining = content_length
    while remaining > 0:
        chunk = stream.read(min(UPLOAD_CHUNK_BYTES, remaining))
        if not chunk:
            return
        remaining -= len(chunk)
        yield chunk


def make_handler(workspace: Path, data_dir: Path, jobs_root: Path) -> type[BaseHTTPRequestHandler]:
    class ReaderHandler(BaseHTTPRequestHandler):
        def _json(self, status: int, payload: Mapping[str, object]) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read_body(self) -> bytes | None:
            """Read a bounded POST body, writing the error response on failure."""
            raw, error = read_limited_body(self)
            if error is not None:
                try:
                    self._json(*error)
                except OSError:
                    return None
                return None
            return raw

        def do_GET(self) -> None:
            if self.path in {"/", "/health", "/api/health"}:
                self._json(200, health())
                return
            if self._handle_console_get():
                return
            if self.path == "/api/retranslate":
                self._json(405, {"ok": False, "error": "method not allowed"})
                return
            route = match_jobs_path(self.path)
            if route is None:
                self.send_error(404)
                return
            kind, job_id = route
            if kind == "collection":
                status, payload = handle_list_jobs(jobs_root=jobs_root)
            elif kind == "item" and job_id is not None:
                status, payload = handle_get_job(job_id, jobs_root=jobs_root)
            else:
                self._json(405, {"ok": False, "error": "method not allowed"})
                return
            self._json(status, payload)

        def do_POST(self) -> None:
            if self._handle_console_post():
                return
            if self.path == "/api/retranslate":
                raw = self._read_body()
                if raw is None:
                    return
                status, payload = handle_retranslate(
                    raw,
                    workspace=workspace,
                    data_dir=data_dir,
                )
                self._json(status, payload)
                return
            route = match_jobs_path(self.path)
            if route is None:
                self.send_error(404)
                return
            kind, job_id = route
            if kind == "collection":
                raw = self._read_body()
                if raw is None:
                    return
                status, payload = handle_submit_job(
                    raw,
                    jobs_root=jobs_root,
                    default_viewer_data_dir=data_dir,
                )
            elif kind == "retry" and job_id is not None:
                status, payload = handle_retry_job(job_id, jobs_root=jobs_root)
            else:
                self._json(405, {"ok": False, "error": "method not allowed"})
                return
            self._json(status, payload)

        def do_PUT(self) -> None:
            self._method_not_allowed()

        def do_DELETE(self) -> None:
            self._method_not_allowed()

        def do_PATCH(self) -> None:
            self._method_not_allowed()

        def _handle_console_get(self) -> bool:
            """Answer a console GET route; ``False`` when the path is not one.

            The console surfaces split by ownership: listings are readable, so
            uploads and workspace opens are reported as method-not-allowed
            here rather than falling through to the jobs/404 dispatch.
            """
            if self.path == WORKSPACES_PATH:
                status, payload = handle_list_workspaces(
                    jobs_root=jobs_root,
                    api_workspace=workspace,
                    data_dir=data_dir,
                )
            elif self.path == STATUS_PATH:
                status, payload = handle_status(jobs_root=jobs_root, data_dir=data_dir)
            elif self.path in _POST_ONLY_PATHS:
                self._method_not_allowed()
                return True
            else:
                return False
            self._json(status, payload)
            return True

        def _handle_console_post(self) -> bool:
            """Answer a console POST route; ``False`` when the path is not one.

            ``True`` always means a response was written (including the 405 and
            the upload body-read errors), so the caller never writes twice.
            """
            if self.path in _GET_ONLY_PATHS:
                self._method_not_allowed()
                return True
            if self.path == OPEN_WORKSPACE_PATH:
                raw = self._read_body()
                if raw is not None:
                    status, payload = handle_open_workspace(raw, data_dir=data_dir)
                    self._json(status, payload)
                return True
            if self.path == UPLOADS_PATH:
                self._handle_upload()
                return True
            return False

        def _handle_upload(self) -> None:
            """Stream one POST body into the server-owned upload inbox.

            Deliberately not ``_read_body``: an upload is up to
            ``MAX_UPLOAD_BYTES`` and is streamed, never buffered whole.
            """
            raw_length = self.headers.get("Content-Length")
            content_length: int | None = None
            if raw_length is not None:
                try:
                    content_length = int(raw_length)
                except ValueError:
                    self._json(400, {"ok": False, "error": "invalid content-length"})
                    return
                if content_length < 0:
                    self._json(400, {"ok": False, "error": "invalid content-length"})
                    return
            chunks = (
                upload_chunks(self.rfile, content_length)
                if content_length is not None
                else iter(lambda: self.rfile.read(UPLOAD_CHUNK_BYTES), b"")
            )
            previous_timeout = self.connection.gettimeout()
            try:
                self.connection.settimeout(UPLOAD_READ_TIMEOUT_S)
                status, payload = store_upload(
                    jobs_root=jobs_root,
                    name=self.headers.get("X-Upload-Name"),
                    content_length=content_length,
                    chunks=chunks,
                )
            except (TimeoutError, ConnectionError, OSError):
                self._json(408, {"ok": False, "error": "upload read timed out"})
                return
            finally:
                with contextlib.suppress(OSError):
                    self.connection.settimeout(previous_timeout)
            if status != 200:
                # A rejected upload may leave body bytes unread, so this
                # connection can no longer be reused for another request.
                self.close_connection = True
            self._json(status, payload)

        def _method_not_allowed(self) -> None:
            if (
                self.path in _CONSOLE_PATHS
                or self.path == "/api/retranslate"
                or match_jobs_path(self.path) is not None
            ):
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
    parser.add_argument("--jobs-root", type=Path, default=Path(".jobs"))
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    server = ThreadingHTTPServer(
        ("127.0.0.1", args.port),
        make_handler(args.workspace, args.data_dir, args.jobs_root),
    )
    print(f"api listening on http://127.0.0.1:{args.port}/health", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
