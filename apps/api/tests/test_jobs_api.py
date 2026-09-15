# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false
"""M8 batch B job API: HTTP contract for /api/jobs and /api/jobs/<id>[/retry].

Runs a real ThreadingHTTPServer on an ephemeral port against a real jobs
root, so submission, listing, inspection, retry, method, and size limits are
exercised end to end. No worker runs here: retry transitions are staged by
claiming and finishing the record directly.
"""

from __future__ import annotations

import json
import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from typing import TYPE_CHECKING, cast

import pytest
from paper_api.__main__ import make_handler
from paper_api.retranslate import MAX_BODY_BYTES
from pdf_pipeline.jobs import claim_next, finish_job

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


@pytest.fixture
def jobs_root(tmp_path: Path) -> Path:
    return tmp_path / "jobs"


@pytest.fixture
def source_pdf(tmp_path: Path) -> Path:
    path = tmp_path / "paper.pdf"
    path.write_bytes(b"%PDF-1.4\n")
    return path


@pytest.fixture
def server(tmp_path: Path, jobs_root: Path) -> Iterator[ThreadingHTTPServer]:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    httpd = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        make_handler(workspace, tmp_path / "data", jobs_root),
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
) -> tuple[int, dict[str, object] | None]:
    connection = HTTPConnection("127.0.0.1", server.server_address[1], timeout=10)
    try:
        connection.request(method, path, body=body)
        response = connection.getresponse()
        payload = response.read()
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            parsed = None
        return response.status, parsed if isinstance(parsed, dict) else None
    finally:
        connection.close()


def _submit(
    server: ThreadingHTTPServer,
    tmp_path: Path,
    source: Path,
    *,
    viewer_data_dir: Path | None = None,
) -> dict[str, object]:
    body: dict[str, object] = {
        "source": str(source),
        "workspace": str(tmp_path / "ws"),
    }
    if viewer_data_dir is not None:
        body["viewerDataDir"] = str(viewer_data_dir)
    status, payload = call(server, "POST", "/api/jobs", json.dumps(body).encode())
    assert status == 202
    assert payload is not None
    job = payload["job"]
    assert isinstance(job, dict)
    return cast("dict[str, object]", job)


def test_submit_job_returns_202_and_persists(
    server: ThreadingHTTPServer, jobs_root: Path, source_pdf: Path, tmp_path: Path
) -> None:
    viewer = tmp_path / "viewer"

    job = _submit(server, tmp_path, source_pdf, viewer_data_dir=viewer)

    assert job["status"] == "queued"
    assert job["attempt"] == 1
    assert job["source"] == str(source_pdf)
    assert job["workspace"] == str(tmp_path / "ws")
    assert job["viewerDataDir"] == str(viewer)
    assert (jobs_root / "queued" / f"{job['id']}.json").is_file()


def test_submit_omitted_viewer_data_dir_defaults_to_server_data_dir(
    server: ThreadingHTTPServer, source_pdf: Path, tmp_path: Path
) -> None:
    job = _submit(server, tmp_path, source_pdf)

    assert job["viewerDataDir"] == str(tmp_path / "data")


def test_submit_explicit_viewer_data_dir_overrides_default(
    server: ThreadingHTTPServer, source_pdf: Path, tmp_path: Path
) -> None:
    explicit = tmp_path / "other-viewer"

    job = _submit(server, tmp_path, source_pdf, viewer_data_dir=explicit)

    assert job["viewerDataDir"] == str(explicit)


def test_submit_null_viewer_data_dir_falls_back_to_default(
    server: ThreadingHTTPServer, source_pdf: Path, tmp_path: Path
) -> None:
    body = json.dumps(
        {
            "source": str(source_pdf),
            "workspace": str(tmp_path / "ws"),
            "viewerDataDir": None,
        }
    ).encode()
    status, payload = call(server, "POST", "/api/jobs", body)

    assert status == 202
    assert payload is not None
    job = payload["job"]
    assert isinstance(job, dict)
    assert job["viewerDataDir"] == str(tmp_path / "data")


def test_submit_job_rejects_bad_requests(
    server: ThreadingHTTPServer, source_pdf: Path, tmp_path: Path
) -> None:
    workspace = str(tmp_path / "ws")
    valid = {"source": str(source_pdf), "workspace": workspace}
    cases = [
        b"not json",
        json.dumps({"workspace": workspace}).encode(),
        json.dumps({"source": str(source_pdf)}).encode(),
        json.dumps({"source": "relative.pdf", "workspace": workspace}).encode(),
        json.dumps({"source": str(source_pdf), "workspace": "relative"}).encode(),
        json.dumps({"source": str(tmp_path / "missing.pdf"), "workspace": workspace}).encode(),
        json.dumps({"source": str(source_pdf), "workspace": 5}).encode(),
        json.dumps({**valid, "viewerDataDir": 5}).encode(),
        json.dumps({**valid, "viewerDataDir": "relative"}).encode(),
        json.dumps({"source": "", "workspace": workspace}).encode(),
    ]
    for body in cases:
        status, payload = call(server, "POST", "/api/jobs", body)
        assert status == 400, body
        assert payload is not None
        assert payload["ok"] is False


def test_submit_body_size_limit_is_413(
    server: ThreadingHTTPServer, source_pdf: Path, tmp_path: Path
) -> None:
    body = json.dumps(
        {
            "source": str(source_pdf),
            "workspace": str(tmp_path / "ws"),
            "pad": "x" * (MAX_BODY_BYTES + 10),
        }
    ).encode()

    status, payload = call(server, "POST", "/api/jobs", body)

    assert status == 413
    assert payload is not None
    assert payload["ok"] is False


def test_list_and_get_job(server: ThreadingHTTPServer, source_pdf: Path, tmp_path: Path) -> None:
    job = _submit(server, tmp_path, source_pdf)
    job_id = str(job["id"])

    status, payload = call(server, "GET", "/api/jobs")
    assert status == 200
    assert payload is not None
    listed = cast("list[dict[str, object]]", payload["jobs"])
    assert [entry["id"] for entry in listed] == [job_id]

    status, payload = call(server, "GET", f"/api/jobs/{job_id}")
    assert status == 200
    assert payload is not None
    fetched = cast("dict[str, object]", payload["job"])
    assert fetched["id"] == job_id
    assert fetched["status"] == "queued"


def test_unknown_job_is_404(server: ThreadingHTTPServer) -> None:
    status, _payload = call(server, "GET", f"/api/jobs/{'0' * 32}")
    assert status == 404
    status, _payload = call(server, "GET", "/api/jobs/not-an-id")
    assert status == 404


def test_retry_transitions(
    server: ThreadingHTTPServer, jobs_root: Path, source_pdf: Path, tmp_path: Path
) -> None:
    job = _submit(server, tmp_path, source_pdf)
    job_id = str(job["id"])

    # Queued jobs are not retryable.
    status, payload = call(server, "POST", f"/api/jobs/{job_id}/retry")
    assert status == 409
    assert payload is not None
    assert payload["ok"] is False

    claim = claim_next(jobs_root)
    assert claim is not None
    finish_job(jobs_root, claim.job, error="boom", stage="render")
    claim.release()

    status, payload = call(server, "POST", f"/api/jobs/{job_id}/retry")
    assert status == 202
    assert payload is not None
    retried = cast("dict[str, object]", payload["job"])
    assert retried["status"] == "queued"
    assert retried["attempt"] == 2
    assert retried["error"] is None

    status, _payload = call(server, "POST", f"/api/jobs/{'0' * 32}/retry")
    assert status == 404


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("PUT", "/api/jobs"),
        ("DELETE", "/api/jobs"),
        ("POST", f"/api/jobs/{'0' * 32}"),
        ("GET", f"/api/jobs/{'0' * 32}/retry"),
        ("PUT", f"/api/jobs/{'0' * 32}/retry"),
    ],
)
def test_wrong_method_is_405(server: ThreadingHTTPServer, method: str, path: str) -> None:
    status, payload = call(server, method, path, b"{}")

    assert status == 405
    assert payload is not None
    assert payload["ok"] is False
