# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false
"""Job queue, claim locks, retry, and failure-issue tests (M8 batch B).

Pure filesystem: no pipeline run, no threads. The worker behaviour lives in
``test_job_worker.py``.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from document_model.generated import schema_models as generated
from pdf_pipeline.jobs import (
    FINISHED_DIR,
    QUEUED_DIR,
    RUNNING_DIR,
    JobError,
    JobNotFoundError,
    JobRecord,
    JobStateError,
    JobStatus,
    JobVersionError,
    claim_next,
    create_job,
    finish_job,
    get_job,
    job_failure_issue,
    list_jobs,
    recover_running,
    retry_job,
)
from pdf_pipeline.workspace import Stage

if TYPE_CHECKING:
    from pathlib import Path

_JOB_ID = re.compile(r"[0-9a-f]{32}")

_JOB_COUNTER = iter(range(1000))


def _write_raw(root: Path, subdir: str, payload: dict[str, object]) -> None:
    directory = root / subdir
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{payload['id']}.json").write_text(json.dumps(payload), encoding="utf-8")


def _queued(root: Path, tmp_path: Path, workspace: Path | None = None) -> JobRecord:
    moment = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=next(_JOB_COUNTER))
    return create_job(
        root,
        source=tmp_path / "paper.pdf",
        workspace=workspace if workspace is not None else tmp_path / "ws",
        now=moment,
    )


def test_create_and_get_job_round_trip(tmp_path: Path) -> None:
    root = tmp_path / "jobs"
    record = create_job(root, source=tmp_path / "paper.pdf", workspace=tmp_path / "ws")

    assert _JOB_ID.fullmatch(record.id) is not None
    assert record.status is JobStatus.QUEUED
    assert record.attempt == 1
    assert record.stage is None
    assert record.error is None
    assert record.issues == ()
    stored = root / QUEUED_DIR / f"{record.id}.json"
    assert stored.is_file()
    assert json.loads(stored.read_text(encoding="utf-8"))["jobVersion"] == "0.1.0"
    assert get_job(root, record.id) == record
    assert list_jobs(root) == [record]


def test_job_version_mismatch_rejected(tmp_path: Path) -> None:
    root = tmp_path / "jobs"
    record = _queued(root, tmp_path)
    (root / QUEUED_DIR / f"{record.id}.json").unlink()
    payload = record.to_json()
    payload["jobVersion"] = "0.0.1"
    _write_raw(root, FINISHED_DIR, payload)

    with pytest.raises(JobVersionError):
        get_job(root, record.id)


def test_invalid_job_id_is_not_found(tmp_path: Path) -> None:
    root = tmp_path / "jobs"
    for candidate in ("../../etc/passwd", "ZZZ", ""):
        with pytest.raises(JobNotFoundError):
            get_job(root, candidate)


def test_list_jobs_dedupes_and_sorts(tmp_path: Path) -> None:
    root = tmp_path / "jobs"
    first = _queued(root, tmp_path)
    second = _queued(root, tmp_path)
    # A crash window can leave the same id visible in two directories; the
    # queued copy is the authoritative one.
    stale = second.to_json()
    stale["status"] = JobStatus.SUCCEEDED.value
    _write_raw(root, FINISHED_DIR, stale)

    records = list_jobs(root)

    assert [record.id for record in records] == [first.id, second.id]
    assert [record.status for record in records] == [JobStatus.QUEUED, JobStatus.QUEUED]


def test_claim_moves_job_to_running_and_is_exclusive(tmp_path: Path) -> None:
    root = tmp_path / "jobs"
    record = _queued(root, tmp_path)

    claim = claim_next(root)
    assert claim is not None
    assert claim.job.id == record.id
    assert claim.job.status is JobStatus.RUNNING
    assert not (root / QUEUED_DIR / f"{record.id}.json").exists()
    assert (root / RUNNING_DIR / f"{record.id}.json").is_file()
    assert get_job(root, record.id).status is JobStatus.RUNNING
    assert claim_next(root) is None
    claim.release()
    assert claim_next(root) is None


def test_claim_serializes_same_workspace(tmp_path: Path) -> None:
    root = tmp_path / "jobs"
    workspace = tmp_path / "ws"
    first = _queued(root, tmp_path, workspace)
    second = _queued(root, tmp_path, workspace)

    claim = claim_next(root)
    assert claim is not None
    assert claim.job.id == first.id
    # Same workspace: the second job waits even though its own lock is free.
    assert claim_next(root) is None
    claim.release()

    next_claim = claim_next(root)
    assert next_claim is not None
    assert next_claim.job.id == second.id
    next_claim.release()


def test_claim_allows_parallel_workspaces(tmp_path: Path) -> None:
    root = tmp_path / "jobs"
    first = _queued(root, tmp_path, tmp_path / "ws-a")
    second = _queued(root, tmp_path, tmp_path / "ws-b")

    claim_a = claim_next(root)
    claim_b = claim_next(root)

    assert claim_a is not None
    assert claim_b is not None
    assert {claim_a.job.id, claim_b.job.id} == {first.id, second.id}
    claim_a.release()
    claim_b.release()


def test_finish_records_success_and_failure(tmp_path: Path) -> None:
    root = tmp_path / "jobs"
    ok_record = _queued(root, tmp_path)
    failed_record = _queued(root, tmp_path)

    ok_claim = claim_next(root)
    assert ok_claim is not None
    ok_final = finish_job(root, ok_claim.job, error=None, stage=None)
    ok_claim.release()
    assert ok_final.status is JobStatus.SUCCEEDED
    assert (root / FINISHED_DIR / f"{ok_record.id}.json").is_file()
    assert get_job(root, ok_record.id).status is JobStatus.SUCCEEDED

    failed_claim = claim_next(root)
    assert failed_claim is not None
    issue = job_failure_issue(
        error=RuntimeError("boom"), job_id=failed_claim.job.id, stage=Stage.RENDER
    )
    failed_final = finish_job(
        root, failed_claim.job, error="boom", stage=Stage.RENDER.value, issues=[issue]
    )
    failed_claim.release()

    assert failed_final.status is JobStatus.FAILED
    stored = get_job(root, failed_record.id)
    assert stored.error == "boom"
    assert stored.stage == Stage.RENDER.value
    assert stored.issues == (issue,)


@pytest.mark.parametrize(
    ("stage", "category", "severity", "producer", "recoverable"),
    [
        (Stage.SEMANTIC, "SECTION_STRUCTURE", "ERROR", "pdf_pipeline.semantic", True),
        (Stage.INGEST, "PHYSICAL_EXTRACTION", "ERROR", "pdf_pipeline.ingest", True),
        (None, "PHYSICAL_EXTRACTION", "FATAL", "pdf_pipeline.orchestrator", False),
    ],
)
def test_failure_issue_conforms_to_canonical_schema(
    stage: Stage | None,
    category: str,
    severity: str,
    producer: str,
    recoverable: bool,
) -> None:
    job_id = "0123456789abcdef0123456789abcdef"
    issue = job_failure_issue(error=RuntimeError("boom"), job_id=job_id, stage=stage)

    parsed = generated.Issue.model_validate(issue)
    assert parsed.message == "boom"
    assert parsed.affectedIds == [job_id]
    assert issue["category"] == category
    assert issue["severity"] == severity
    assert issue["producer"] == producer
    assert issue["recoverable"] is recoverable


def test_retry_requires_failed_status(tmp_path: Path) -> None:
    root = tmp_path / "jobs"
    queued_record = _queued(root, tmp_path)
    with pytest.raises(JobStateError):
        retry_job(root, queued_record.id)

    succeeded_record = _queued(root, tmp_path)
    claim = claim_next(root)
    assert claim is not None
    assert claim.job.id == queued_record.id
    finish_job(root, claim.job, error=None, stage=None)
    claim.release()
    succeeded = claim_next(root)
    assert succeeded is not None
    assert succeeded.job.id == succeeded_record.id
    finish_job(root, succeeded.job, error=None, stage=None)
    succeeded.release()
    with pytest.raises(JobStateError):
        retry_job(root, succeeded_record.id)


def test_retry_requeues_with_attempt_incremented(tmp_path: Path) -> None:
    root = tmp_path / "jobs"
    record = _queued(root, tmp_path)
    claim = claim_next(root)
    assert claim is not None
    finish_job(root, claim.job, error="boom", stage=Stage.TRANSLATE.value, issues=[{"id": "x"}])
    claim.release()

    requeued = retry_job(root, record.id)

    assert requeued.status is JobStatus.QUEUED
    assert requeued.attempt == 2
    assert requeued.stage is None
    assert requeued.error is None
    assert requeued.issues == ()
    assert (root / QUEUED_DIR / f"{record.id}.json").is_file()
    assert not (root / FINISHED_DIR / f"{record.id}.json").exists()
    assert get_job(root, record.id) == requeued


def test_recover_running_requeues_when_owner_gone(tmp_path: Path) -> None:
    root = tmp_path / "jobs"
    record = _queued(root, tmp_path)
    (root / QUEUED_DIR / f"{record.id}.json").unlink()
    payload = record.to_json()
    payload["status"] = JobStatus.RUNNING.value
    _write_raw(root, RUNNING_DIR, payload)

    assert recover_running(root) == [record.id]

    recovered = get_job(root, record.id)
    assert recovered.status is JobStatus.QUEUED
    assert recovered.attempt == 1
    assert not (root / RUNNING_DIR / f"{record.id}.json").exists()


def test_recover_running_skips_live_owner(tmp_path: Path) -> None:
    root = tmp_path / "jobs"
    record = _queued(root, tmp_path)
    claim = claim_next(root)
    assert claim is not None

    assert recover_running(root) == []
    assert (root / RUNNING_DIR / f"{record.id}.json").is_file()
    claim.release()


def test_corrupt_record_is_job_error(tmp_path: Path) -> None:
    root = tmp_path / "jobs"
    directory = root / QUEUED_DIR
    directory.mkdir(parents=True)
    (directory / f"{'a' * 32}.json").write_text("{not json", encoding="utf-8")

    with pytest.raises(JobError):
        get_job(root, "a" * 32)
