# pyright: reportPrivateUsage=false
"""Deterministic regressions for M8 queue and publication interleavings."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from pdf_pipeline import jobs, pipeline
from pdf_pipeline.locks import FileLock, resource_lock, resource_lock_path


def test_contended_claims_close_every_descriptor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    opened: set[int] = set()
    original_open, original_close = os.open, os.close

    def track_open(path: str | bytes | os.PathLike[str], flags: int, mode: int = 0o777) -> int:
        fd = original_open(path, flags, mode)
        opened.add(fd)
        return fd

    def track_close(fd: int) -> None:
        opened.discard(fd)
        original_close(fd)

    monkeypatch.setattr(os, "open", track_open)
    monkeypatch.setattr(os, "close", track_close)
    root = tmp_path / "jobs"
    for _ in range(2):
        jobs.create_job(root, source=tmp_path / "source", workspace=tmp_path / "ws")
    claim = jobs.claim_next(root)
    assert claim is not None
    try:
        count = len(opened)
        for _ in range(20):
            assert jobs.claim_next(root) is None
        assert len(opened) == count
    finally:
        claim.release()
    assert not opened


def test_retry_cannot_delete_new_claim(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "jobs"
    job = jobs.create_job(root, source=tmp_path / "source", workspace=tmp_path / "ws")
    jobs.finish_job(root, job, error="failed", stage=None)
    original_write = jobs._write_record

    def interleave(root: Path, name: str, record: jobs.JobRecord) -> None:
        original_write(root, name, record)
        if name == jobs.QUEUED_DIR:
            assert jobs.claim_next(root) is None

    monkeypatch.setattr(jobs, "_write_record", interleave)
    retried = jobs.retry_job(root, job.id)
    assert retried.attempt == 2
    claim = jobs.claim_next(root)
    assert claim is not None
    try:
        assert jobs.get_job(root, job.id).status is jobs.JobStatus.RUNNING
        assert jobs.recover_running(root) == []
    finally:
        claim.release()


def test_claim_write_failure_releases_locks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "jobs"
    job = jobs.create_job(root, source=tmp_path / "source", workspace=tmp_path / "ws")
    original_write = jobs._write_record

    def fail_write(root: Path, name: str, record: jobs.JobRecord) -> None:
        if name == jobs.RUNNING_DIR:
            raise OSError("disk full")
        original_write(root, name, record)

    with monkeypatch.context() as patch:
        patch.setattr(jobs, "_write_record", fail_write)
        with pytest.raises(OSError, match="disk full"):
            jobs.claim_next(root)
    assert jobs.recover_running(root) == [job.id]
    claim = jobs.claim_next(root)
    assert claim is not None
    claim.release()


def test_resource_lock_excludes_other_process_and_is_reentrant(tmp_path: Path) -> None:
    code = """
import sys
from pathlib import Path
from pdf_pipeline.locks import FileLock, resource_lock_path
lock = FileLock(resource_lock_path(Path(sys.argv[1]), 'workspace'))
try:
    print(lock.acquire(blocking=False))
finally:
    lock.release()
"""
    with resource_lock(tmp_path, "workspace"), resource_lock(tmp_path / ".", "workspace"):
        result = subprocess.run(  # noqa: S603 — fixed interpreter and local test code
            [sys.executable, "-c", code, str(tmp_path)], capture_output=True, text=True, check=True
        )
        assert result.stdout.strip() == "False"
    result = subprocess.run(  # noqa: S603 — fixed interpreter and local test code
        [sys.executable, "-c", code, str(tmp_path)], capture_output=True, text=True, check=True
    )
    assert result.stdout.strip() == "True"


def test_parallel_publish_keeps_committed_revisions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    staged = threading.Event()
    competing = threading.Event()
    original_replace = pipeline._replace_files_with_rollback
    original_acquire = FileLock.acquire
    first_thread: int | None = None

    def acquire(lock: FileLock, *, blocking: bool) -> bool:
        if first_thread is not None and threading.get_ident() != first_thread:
            competing.set()
        return original_acquire(lock, blocking=blocking)

    def replace(contents: dict[Path, bytes], *, commit_last: Path) -> None:
        nonlocal first_thread
        if first_thread is None:
            first_thread = threading.get_ident()
            staged.set()
            assert competing.wait(5)
        original_replace(contents, commit_last=commit_last)

    def publish(tag: str) -> str:
        return pipeline._publish_viewer_revision(
            tmp_path,
            mapping_text=tag,
            meta_text=tag,
            source_pdf=tag.encode(),
            target_pdf=tag.encode(),
        )

    monkeypatch.setattr(FileLock, "acquire", acquire)
    monkeypatch.setattr(pipeline, "_replace_files_with_rollback", replace)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(publish, "A")
        assert staged.wait(5)
        second = pool.submit(publish, "B")
        revisions = [first.result(timeout=10), second.result(timeout=10)]
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert manifest["revision"] == revisions[1]
    for revision, text in zip(revisions, (b"A", b"B"), strict=True):
        assert (tmp_path / "revisions" / revision / "target.pdf").read_bytes() == text
    assert (tmp_path / "target.pdf").read_bytes() == b"B"


@pytest.mark.parametrize("operation", ["pipeline", "retranslate"])
def test_all_workspace_entrypoints_take_the_same_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    acquired: list[Path] = []
    original_open = os.open

    def track_open(path: str | bytes | os.PathLike[str], flags: int, mode: int = 0o777) -> int:
        if isinstance(path, Path):
            acquired.append(path)
        return original_open(path, flags, mode)

    monkeypatch.setattr(os, "open", track_open)
    if operation == "pipeline":
        with pytest.raises(FileNotFoundError):
            pipeline.run_pipeline(tmp_path / "missing.pdf", tmp_path / "ws")
    else:
        with pytest.raises(FileNotFoundError):
            pipeline.rerender_workspace(
                tmp_path / "ws", viewer_data_dir=tmp_path / "viewer", node_ids={"node"}
            )
    assert resource_lock_path(tmp_path / "ws", "workspace") in acquired
    lock = FileLock(resource_lock_path(tmp_path / "ws", "workspace"))
    try:
        assert lock.acquire(blocking=False)
    finally:
        lock.release()
