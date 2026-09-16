# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false
"""Worker liveness record (console `status` surface).

The heartbeat answers a question the queue cannot: a running record means the
worker is alive, an absent one means nothing serves this root, and a stale one
means the worker died mid-run. These tests pin the record shape, its
degradation on garbage, and the worker lifecycle that publishes and removes it.
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

import pytest
from pdf_pipeline.jobs import (
    HEARTBEAT_VERSION,
    JobWorker,
    clear_heartbeat,
    create_job,
    heartbeat_path,
    read_heartbeat,
    write_heartbeat,
)


@pytest.fixture
def smoke_pdf() -> Path:
    fixture = Path(__file__).resolve().parents[4] / "tests/fixtures/source/latex/build/smoke.pdf"
    if not fixture.exists():
        pytest.skip("smoke fixture PDF not built; run `just latex-smoke`")
    return fixture


def _started_at() -> str:
    return "2026-09-16T10:00:00+00:00"


def test_write_heartbeat_round_trips(tmp_path: Path) -> None:
    payload = write_heartbeat(
        tmp_path, started_at=_started_at(), concurrency=2, running=1, now=None
    )

    assert set(payload) == {
        "heartbeatVersion",
        "pid",
        "startedAt",
        "updatedAt",
        "concurrency",
        "running",
    }
    assert payload["heartbeatVersion"] == HEARTBEAT_VERSION
    assert payload["pid"] == os.getpid()
    assert payload["startedAt"] == _started_at()
    assert payload["concurrency"] == 2
    assert payload["running"] == 1
    assert read_heartbeat(tmp_path) == payload


def test_read_heartbeat_rejects_garbage_instead_of_defaulting(tmp_path: Path) -> None:
    assert read_heartbeat(tmp_path) is None

    heartbeat_path(tmp_path).write_text("not json", encoding="utf-8")
    assert read_heartbeat(tmp_path) is None

    heartbeat_path(tmp_path).write_text(json.dumps(["a"]), encoding="utf-8")
    assert read_heartbeat(tmp_path) is None

    complete = {
        "heartbeatVersion": HEARTBEAT_VERSION,
        "pid": os.getpid(),
        "startedAt": _started_at(),
        "updatedAt": _started_at(),
        "concurrency": 1,
        "running": 0,
    }
    for key, value in (("pid", "4711"), ("running", None), ("updatedAt", 5)):
        broken = {**complete, key: value}
        heartbeat_path(tmp_path).write_text(json.dumps(broken), encoding="utf-8")
        assert read_heartbeat(tmp_path) is None, key

    missing = {key: value for key, value in complete.items() if key != "concurrency"}
    heartbeat_path(tmp_path).write_text(json.dumps(missing), encoding="utf-8")
    assert read_heartbeat(tmp_path) is None


def test_clear_heartbeat_is_idempotent(tmp_path: Path) -> None:
    write_heartbeat(tmp_path, started_at=_started_at(), concurrency=1, running=0)

    clear_heartbeat(tmp_path)
    clear_heartbeat(tmp_path)

    assert read_heartbeat(tmp_path) is None
    assert not heartbeat_path(tmp_path).exists()


def test_one_shot_run_leaves_no_liveness_record(
    tmp_path: Path, smoke_pdf: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def runner(source: Path, workspace: Path, viewer_data_dir: Path | None) -> dict[str, Path]:
        del source, workspace, viewer_data_dir
        return {}

    root = tmp_path / "jobs"
    create_job(root, source=smoke_pdf, workspace=tmp_path / "ws")

    assert JobWorker(root, runner=runner).run_once() == 1

    # `--once` must not leave a file that reads as a live worker.
    assert read_heartbeat(root) is None


def test_forever_worker_advertises_itself_while_running(tmp_path: Path, smoke_pdf: Path) -> None:
    root = tmp_path / "jobs"
    started = threading.Event()
    release = threading.Event()

    def runner(source: Path, workspace: Path, viewer_data_dir: Path | None) -> dict[str, Path]:
        del source, workspace, viewer_data_dir
        started.set()
        release.wait(timeout=10)
        return {}

    create_job(root, source=smoke_pdf, workspace=tmp_path / "ws")
    worker = JobWorker(root, runner=runner)
    stop = threading.Event()
    beats = threading.Thread(target=worker.run_forever, args=(stop,), daemon=True)
    beats.start()
    try:
        assert started.wait(timeout=10)
        assert read_heartbeat(root) is not None
        # The beat interval, not the job, decides when the in-flight count is
        # republished; poll across one interval instead of racing it.
        record = _wait_for_running(root, 1)
        assert record is not None
        assert record["pid"] == os.getpid()
        assert record["concurrency"] == 1
    finally:
        release.set()
        stop.set()
        beats.join(timeout=10)

    assert read_heartbeat(root) is None


def _wait_for_running(root: Path, running: int, timeout: float = 10.0) -> dict[str, object] | None:
    deadline = time.monotonic() + timeout
    record = read_heartbeat(root)
    while time.monotonic() < deadline:
        if record is not None and record["running"] == running:
            return record
        time.sleep(0.05)
        record = read_heartbeat(root)
    return record
