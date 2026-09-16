# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false
"""Console `status` surface over HTTP: one payload for the whole stack.

Runs a real ThreadingHTTPServer on an ephemeral port against a real jobs root,
so the queue counts and the oldest-queued timestamp come from real records and
the worker section from a real heartbeat file. A heartbeat is the only signal
that separates "no worker" from "worker died mid-job".
"""

from __future__ import annotations

import json
import os
import threading
from datetime import UTC, datetime, timedelta
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from typing import TYPE_CHECKING, cast

import pytest
from paper_api.__main__ import make_handler
from pdf_pipeline.jobs import HEARTBEAT_STALE_S, claim_next, create_job, finish_job, write_heartbeat

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

QUEUED_AT = "2026-09-16T10:00:00+00:00"


@pytest.fixture
def jobs_root(tmp_path: Path) -> Path:
    """One finished job and one still queued, oldest first."""
    root = tmp_path / "jobs"
    source = tmp_path / "paper.pdf"
    source.write_bytes(b"%PDF-1.4\n")
    create_job(
        root,
        source=source,
        workspace=tmp_path / "ws-old",
        now=datetime.fromisoformat("2026-09-16T09:00:00+00:00"),
    )
    create_job(
        root,
        source=source,
        workspace=tmp_path / "ws-new",
        now=datetime.fromisoformat(QUEUED_AT),
    )
    claim = claim_next(root)
    assert claim is not None
    finish_job(root, claim.job, error=None, stage=None)
    claim.release()
    return root


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


def call(server: ThreadingHTTPServer, path: str) -> tuple[int, dict[str, object] | None]:
    connection = HTTPConnection("127.0.0.1", server.server_address[1], timeout=10)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        payload = response.read()
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            parsed = None
        return response.status, parsed if isinstance(parsed, dict) else None
    finally:
        connection.close()


def _section(payload: dict[str, object] | None, key: str) -> dict[str, object]:
    assert payload is not None
    return cast("dict[str, object]", payload[key])


def test_status_reports_the_whole_stack(
    server: ThreadingHTTPServer, jobs_root: Path, tmp_path: Path
) -> None:
    write_heartbeat(jobs_root, started_at="2026-09-16T11:00:00+00:00", concurrency=1, running=0)
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "manifest.json").write_text(
        json.dumps({"revision": "rev-1", "workspace": str(tmp_path / "ws-old")}),
        encoding="utf-8",
    )

    status, payload = call(server, "/api/status")

    assert status == 200
    assert payload is not None
    assert payload["ok"] is True
    assert payload["api"] == {"status": "ok", "service": "api"}

    worker = _section(payload, "worker")
    assert worker["present"] is True
    assert worker["alive"] is True
    assert worker["pid"] == os.getpid()
    assert worker["startedAt"] == "2026-09-16T11:00:00+00:00"
    assert worker["concurrency"] == 1
    assert worker["running"] == 0
    age = worker["ageSeconds"]
    assert isinstance(age, float)
    assert 0 <= age < HEARTBEAT_STALE_S

    assert payload["jobs"] == {
        "queued": 1,
        "running": 0,
        "succeeded": 1,
        "failed": 0,
        "oldestQueuedAt": QUEUED_AT,
    }
    assert payload["viewer"] == {"revision": "rev-1", "workspace": str(tmp_path / "ws-old")}


def test_status_marks_a_silent_worker_stale(server: ThreadingHTTPServer, jobs_root: Path) -> None:
    write_heartbeat(
        jobs_root,
        started_at="2026-09-16T11:00:00+00:00",
        concurrency=1,
        running=1,
        now=datetime.now(UTC) - timedelta(seconds=HEARTBEAT_STALE_S + 1),
    )

    status, payload = call(server, "/api/status")
    assert status == 200

    worker = _section(payload, "worker")
    assert worker["present"] is True
    assert worker["alive"] is False
    age = worker["ageSeconds"]
    assert isinstance(age, float)
    assert age > HEARTBEAT_STALE_S


def test_status_reports_an_absent_worker(server: ThreadingHTTPServer, jobs_root: Path) -> None:
    assert not (jobs_root / "worker.json").exists()

    status, payload = call(server, "/api/status")
    assert status == 200

    assert _section(payload, "worker") == {
        "present": False,
        "alive": False,
        "pid": None,
        "startedAt": None,
        "updatedAt": None,
        "ageSeconds": None,
        "concurrency": None,
        "running": 0,
    }


def test_status_reports_no_published_revision(server: ThreadingHTTPServer) -> None:
    status, payload = call(server, "/api/status")
    assert status == 200

    assert payload is not None
    assert payload["viewer"] is None


def test_wrong_method_on_status_is_405(server: ThreadingHTTPServer) -> None:
    connection = HTTPConnection("127.0.0.1", server.server_address[1], timeout=10)
    try:
        connection.request("POST", "/api/status", body=b"{}")
        response = connection.getresponse()
        payload = json.loads(response.read())
    finally:
        connection.close()

    assert response.status == 405
    assert payload["ok"] is False
