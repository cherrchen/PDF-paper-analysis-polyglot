# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false
"""Console `upload` surface over HTTP: a PDF lands in the server's inbox.

Runs a real ThreadingHTTPServer on an ephemeral port and posts real bytes, so
the content hash, the derived inbox name, and the derived workspace path are
all exercised end to end. The inbox is server-owned: the client cannot choose
where its bytes land, only what they are.
"""

from __future__ import annotations

import hashlib
import json
import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from typing import TYPE_CHECKING

import pytest
from paper_api.__main__ import make_handler
from paper_api.uploads import MAX_UPLOAD_BYTES

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping
    from pathlib import Path

PDF_BYTES = b"%PDF-1.4\n% console upload fixture\n"


@pytest.fixture
def jobs_root(tmp_path: Path) -> Path:
    return tmp_path / "jobs"


@pytest.fixture
def server(tmp_path: Path, jobs_root: Path) -> Iterator[ThreadingHTTPServer]:
    httpd = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        make_handler(tmp_path / "ws", tmp_path / "data", jobs_root),
    )
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield httpd
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


def call(
    server: ThreadingHTTPServer,
    method: str,
    path: str,
    body: bytes | None = None,
    headers: Mapping[str, str] | None = None,
) -> tuple[int, dict[str, object] | None]:
    connection = HTTPConnection("127.0.0.1", server.server_address[1], timeout=10)
    try:
        connection.request(method, path, body=body, headers=dict(headers or {}))
        response = connection.getresponse()
        payload = response.read()
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            parsed = None
        return response.status, parsed if isinstance(parsed, dict) else None
    finally:
        connection.close()


def _part_residue(jobs_root: Path) -> list[Path]:
    inbox = jobs_root / "inbox"
    if not inbox.is_dir():
        return []
    return [path for path in inbox.iterdir() if path.name.endswith(".part")]


def test_upload_stores_the_pdf_and_derives_a_workspace(
    server: ThreadingHTTPServer, jobs_root: Path
) -> None:
    digest = hashlib.sha256(PDF_BYTES).hexdigest()

    status, payload = call(
        server,
        "POST",
        "/api/uploads",
        PDF_BYTES,
        {"X-Upload-Name": "Paper One.pdf", "content-type": "application/pdf"},
    )

    assert status == 200
    assert payload is not None
    assert payload["ok"] is True
    assert payload["sha256"] == digest
    assert payload["bytes"] == len(PDF_BYTES)
    stored = jobs_root / "inbox" / f"Paper-One-{digest[:8]}.pdf"
    assert payload["path"] == str(stored)
    assert stored.read_bytes() == PDF_BYTES
    assert payload["workspace"] == str(jobs_root / "workspaces" / f"Paper-One-{digest[:8]}")
    # The workspace is created by the pipeline, never by the upload.
    assert not (jobs_root / "workspaces").exists()
    assert _part_residue(jobs_root) == []


def test_upload_is_idempotent_for_the_same_file(
    server: ThreadingHTTPServer, jobs_root: Path
) -> None:
    first, first_payload = call(
        server, "POST", "/api/uploads", PDF_BYTES, {"X-Upload-Name": "paper.pdf"}
    )
    second, second_payload = call(
        server, "POST", "/api/uploads", PDF_BYTES, {"X-Upload-Name": "paper.pdf"}
    )

    assert first == second == 200
    assert first_payload is not None
    assert second_payload is not None
    # Content addresses the name, so re-uploading the same document reuses the
    # inbox file and the workspace the auto-submitted job will target.
    assert second_payload["path"] == first_payload["path"]
    assert second_payload["workspace"] == first_payload["workspace"]
    assert sorted(path.name for path in (jobs_root / "inbox").iterdir()) == [
        str(second_payload["path"]).rsplit("/", 1)[-1]
    ]


@pytest.mark.parametrize(
    ("name", "body"),
    [
        (None, PDF_BYTES),
        ("", PDF_BYTES),
        ("notes.txt", PDF_BYTES),
        ("paper.pdf", b"not a pdf at all"),
        ("paper.pdf", b""),
    ],
)
def test_upload_rejects_bad_requests(
    server: ThreadingHTTPServer, jobs_root: Path, name: str | None, body: bytes
) -> None:
    headers = {"content-type": "application/pdf"}
    if name is not None:
        headers["X-Upload-Name"] = name

    status, payload = call(server, "POST", "/api/uploads", body, headers)

    assert status == 400, name
    assert payload is not None
    assert payload["ok"] is False
    assert _part_residue(jobs_root) == []
    if (jobs_root / "inbox").is_dir():
        assert list((jobs_root / "inbox").iterdir()) == []


def test_upload_rejects_an_oversized_declaration(
    server: ThreadingHTTPServer, jobs_root: Path
) -> None:
    status, payload = call(
        server,
        "POST",
        "/api/uploads",
        PDF_BYTES,
        {
            "X-Upload-Name": "paper.pdf",
            "content-type": "application/pdf",
            "Content-Length": str(MAX_UPLOAD_BYTES + 1),
        },
    )

    assert status == 413
    assert payload is not None
    assert payload["ok"] is False
    assert _part_residue(jobs_root) == []


@pytest.mark.parametrize("method", ["PUT", "DELETE", "PATCH"])
def test_wrong_method_on_uploads_is_405(server: ThreadingHTTPServer, method: str) -> None:
    status, payload = call(server, method, "/api/uploads", b"{}")

    assert status == 405
    assert payload is not None
    assert payload["ok"] is False
