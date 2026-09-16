# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false
"""File-backed job queue for the local pipeline (M8 batch B).

A jobs root is a plain directory with four subdirectories:

``queued/``   records waiting for a worker
``running/``  records claimed by a live worker
``finished/`` terminal records (succeeded or failed)
``locks/``    ``flock`` files, one per job and one per workspace

and one optional file, ``worker.json``: the liveness record of whatever
worker is serving this root (``write_heartbeat``). It exists only while a
worker runs, so a reader distinguishes "no worker" from "worker died" by
absence versus age — a queue snapshot alone cannot tell a live worker from a
crashed one.

Each job is one ``<jobId>.json`` record moved between the subdirectories by
atomic rename, so a reader never sees a half-written record and a crash
window never leaves two visible copies (``get_job``/``list_jobs`` prefer the
earliest directory in ``queued > running > finished`` order).

Claiming uses POSIX ``fcntl.flock`` exclusively:

* a per-job lock makes the claim race-free between workers;
* a per-workspace lock serializes jobs that share one workspace directory
  (``lualatex`` writes into a single shared ``build/`` per workspace).

Because a lock belongs to the open file description, the kernel releases it
when the owning process dies. ``recover_running`` therefore distinguishes a
crashed worker (lock free → requeue) from a live one (lock held → leave it).

Recovery only rewinds the *job*; the workspace stage state from batch A
decides which stages actually rerun, so finished artifacts are never lost.
Requeuing is always manual (``retry_job``); there is no automatic retry or
backoff.

POSIX-only by design: ``fcntl.flock`` is available on macOS and Linux (CI is
ubuntu). ``FileLock`` is the single replacement point if Windows support is
ever needed.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import uuid
from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

from pdf_pipeline.locks import FileLock
from pdf_pipeline.workspace import Stage

if TYPE_CHECKING:
    from collections.abc import Sequence

JOB_VERSION = "0.1.0"

QUEUED_DIR = "queued"
RUNNING_DIR = "running"
FINISHED_DIR = "finished"
LOCKS_DIR = "locks"

# Worker liveness record, one per jobs root. A root normally has exactly one
# worker (`just` starts one); two workers on the same root overwrite each
# other's beat, and whichever exits cleanly removes the file. That is
# deliberate: the record answers "is a worker serving this root right now",
# not "which workers exist".
HEARTBEAT_NAME = "worker.json"
HEARTBEAT_VERSION = "0.1.0"
HEARTBEAT_INTERVAL_S = 2.0
HEARTBEAT_STALE_S = 15.0

POLL_INTERVAL_S = 1.0

_JOB_ID_PATTERN = re.compile(r"[0-9a-f]{32}")

# Visible-record priority when the same id lingers in more than one
# directory (only possible inside a crash window between two renames).
_SEARCH_ORDER = (QUEUED_DIR, RUNNING_DIR, FINISHED_DIR)


class JobStatus(StrEnum):
    """Lifecycle of one queued pipeline job."""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class JobError(RuntimeError):
    """Base error for job record problems."""


class JobVersionError(JobError):
    """The record was written by an incompatible job version."""


class JobNotFoundError(JobError):
    """No record with that id exists in the jobs root."""


class JobStateError(JobError):
    """The requested transition is not allowed for the job's status."""


def _now(now: datetime | None) -> str:
    return (now or datetime.now(UTC)).isoformat(timespec="seconds")


def _job_str(data: dict[str, object], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str):
        raise JobError(f"job {key} must be a string")
    return value


def _optional_str(data: dict[str, object], key: str) -> str | None:
    value = data.get(key)
    if value is not None and not isinstance(value, str):
        raise JobError(f"job {key} must be a string or null")
    return value


def _parse_issues(raw: object) -> tuple[dict[str, object], ...]:
    if not isinstance(raw, list):
        raise JobError("job issues must be a list")
    issues: list[dict[str, object]] = []
    for item in raw:
        if not isinstance(item, dict):
            raise JobError("job issue entries must be objects")
        issues.append({str(key): value for key, value in item.items()})
    return tuple(issues)


@dataclass(frozen=True)
class JobRecord:
    """One pipeline job: a source PDF, its workspace, and its outcome."""

    id: str
    status: JobStatus
    source: str
    workspace: str
    viewer_data_dir: str | None
    attempt: int
    created_at: str
    updated_at: str
    stage: str | None = None
    error: str | None = None
    issues: tuple[dict[str, object], ...] = ()

    def to_json(self) -> dict[str, object]:
        return {
            "jobVersion": JOB_VERSION,
            "id": self.id,
            "status": self.status.value,
            "source": self.source,
            "workspace": self.workspace,
            "viewerDataDir": self.viewer_data_dir,
            "attempt": self.attempt,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
            "stage": self.stage,
            "error": self.error,
            "issues": [dict(issue) for issue in self.issues],
        }

    @classmethod
    def from_json(cls, data: object) -> JobRecord:
        if not isinstance(data, dict):
            raise JobError("job record must be an object")
        version = data.get("jobVersion")
        if version != JOB_VERSION:
            raise JobVersionError(
                f"job record version {version!r} is not supported (expected {JOB_VERSION!r})"
            )
        job_id = data.get("id")
        if not isinstance(job_id, str) or _JOB_ID_PATTERN.fullmatch(job_id) is None:
            raise JobError(f"invalid job id: {job_id!r}")
        raw_status = _job_str(data, "status")
        try:
            status = JobStatus(raw_status)
        except ValueError:
            raise JobError(f"unknown job status: {raw_status!r}") from None
        attempt = data.get("attempt")
        if not isinstance(attempt, int) or isinstance(attempt, bool) or attempt < 1:
            raise JobError("job attempt must be a positive integer")
        return cls(
            id=job_id,
            status=status,
            source=_job_str(data, "source"),
            workspace=_job_str(data, "workspace"),
            viewer_data_dir=_optional_str(data, "viewerDataDir"),
            attempt=attempt,
            created_at=_job_str(data, "createdAt"),
            updated_at=_job_str(data, "updatedAt"),
            stage=_optional_str(data, "stage"),
            error=_optional_str(data, "error"),
            issues=_parse_issues(data.get("issues", [])),
        )


def _atomic_write_json(path: Path, data: object) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def _subdir(root: Path, name: str) -> Path:
    path = root / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def _record_path(root: Path, name: str, job_id: str) -> Path:
    return _subdir(root, name) / f"{job_id}.json"


def _validate_job_id(job_id: str) -> str:
    if _JOB_ID_PATTERN.fullmatch(job_id) is None:
        raise JobNotFoundError(f"invalid job id: {job_id!r}")
    return job_id


def _read_record(path: Path) -> JobRecord:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise JobError(f"unreadable job record {path.name}: {error}") from error
    return JobRecord.from_json(payload)


def _write_record(root: Path, name: str, record: JobRecord) -> None:
    _atomic_write_json(_record_path(root, name, record.id), record.to_json())


def _move_job(root: Path, record: JobRecord, name: str) -> None:
    """Publish the record under ``name`` and drop same-id residue elsewhere."""
    _write_record(root, name, record)
    for other in _SEARCH_ORDER:
        if other != name:
            _record_path(root, other, record.id).unlink(missing_ok=True)


def get_job(root: Path, job_id: str) -> JobRecord:
    """Read one record, preferring the earliest directory when it is duplicated."""
    _validate_job_id(job_id)
    for name in _SEARCH_ORDER:
        path = root / name / f"{job_id}.json"
        if path.is_file():
            return _read_record(path)
    raise JobNotFoundError(f"unknown job: {job_id}")


def list_jobs(root: Path) -> list[JobRecord]:
    """Every known record, deduplicated, oldest first."""
    records: dict[str, JobRecord] = {}
    for name in _SEARCH_ORDER:
        for path in sorted((root / name).glob("*.json")):
            job_id = path.stem
            if job_id in records or _JOB_ID_PATTERN.fullmatch(job_id) is None:
                continue
            records[job_id] = _read_record(path)
    return sorted(records.values(), key=lambda record: (record.created_at, record.id))


def create_job(
    root: Path,
    *,
    source: Path,
    workspace: Path,
    viewer_data_dir: Path | None = None,
    now: datetime | None = None,
) -> JobRecord:
    """Queue a fresh job (attempt 1) for the given source and workspace."""
    timestamp = _now(now)
    record = JobRecord(
        id=uuid.uuid4().hex,
        status=JobStatus.QUEUED,
        source=str(source),
        workspace=str(workspace),
        viewer_data_dir=str(viewer_data_dir) if viewer_data_dir is not None else None,
        attempt=1,
        created_at=timestamp,
        updated_at=timestamp,
    )
    _write_record(root, QUEUED_DIR, record)
    return record


def retry_job(root: Path, job_id: str) -> JobRecord:
    """Requeue a failed job. Workspace artifacts are left to the stage state."""
    _validate_job_id(job_id)
    lock = FileLock(_lock_path(root, job_id))
    try:
        if not lock.acquire(blocking=False):
            raise JobStateError(f"job {job_id} is busy")
        record = get_job(root, job_id)
        if record.status is not JobStatus.FAILED:
            raise JobStateError(
                f"job {job_id} is {record.status.value}; only failed jobs can be retried"
            )
        requeued = replace(
            record,
            status=JobStatus.QUEUED,
            attempt=record.attempt + 1,
            stage=None,
            error=None,
            issues=(),
            updated_at=_now(None),
        )
        _move_job(root, requeued, QUEUED_DIR)
        return requeued
    finally:
        lock.release()


def _lock_path(root: Path, job_id: str) -> Path:
    return root / LOCKS_DIR / f"job-{job_id}.lock"


def _workspace_lock_path(root: Path, workspace: str) -> Path:
    digest = hashlib.sha256(str(Path(workspace).resolve()).encode("utf-8")).hexdigest()
    return root / LOCKS_DIR / f"workspace-{digest}.lock"


class JobClaim:
    """One claimed job plus the two exclusive locks held while it runs."""

    def __init__(self, job: JobRecord, job_lock: FileLock, workspace_lock: FileLock) -> None:
        self.job = job
        self._job_lock = job_lock
        self._workspace_lock = workspace_lock

    def release(self) -> None:
        self._job_lock.release()
        self._workspace_lock.release()


def claim_next(root: Path) -> JobClaim | None:
    """Claim the oldest queued job whose job and workspace locks are free."""
    queued = root / QUEUED_DIR
    candidates: list[JobRecord] = []
    if queued.is_dir():
        for path in sorted(queued.glob("*.json")):
            if _JOB_ID_PATTERN.fullmatch(path.stem) is None:
                continue
            try:
                candidates.append(_read_record(path))
            except JobError:
                if path.exists():
                    raise
    candidates.sort(key=lambda record: (record.created_at, record.id))

    for candidate in candidates:
        job_lock = FileLock(_lock_path(root, candidate.id))
        workspace_lock: FileLock | None = None
        transferred = False
        try:
            if not job_lock.acquire(blocking=False):
                continue
            # The queue snapshot can predate a retry or another worker's claim.
            path = queued / f"{candidate.id}.json"
            if not path.is_file():
                continue
            record = _read_record(path)
            workspace_lock = FileLock(_workspace_lock_path(root, record.workspace))
            if not workspace_lock.acquire(blocking=False):
                continue
            path.replace(_subdir(root, RUNNING_DIR) / path.name)
            claimed = replace(record, status=JobStatus.RUNNING, updated_at=_now(None))
            _write_record(root, RUNNING_DIR, claimed)
            transferred = True
            return JobClaim(claimed, job_lock, workspace_lock)
        finally:
            if not transferred:
                if workspace_lock is not None:
                    workspace_lock.release()
                job_lock.release()
    return None


def recover_running(root: Path) -> list[str]:
    """Requeue running jobs whose owning worker is gone (its lock is free)."""
    recovered: list[str] = []
    running = root / RUNNING_DIR
    if not running.is_dir():
        return recovered
    for path in sorted(running.glob("*.json")):
        job_id = path.stem
        if _JOB_ID_PATTERN.fullmatch(job_id) is None:
            continue
        lock = FileLock(_lock_path(root, job_id))
        try:
            if not lock.acquire(blocking=False):
                continue
            requeued = replace(_read_record(path), status=JobStatus.QUEUED, updated_at=_now(None))
            _move_job(root, requeued, QUEUED_DIR)
            recovered.append(job_id)
        finally:
            lock.release()
    return recovered


def finish_job(
    root: Path,
    job: JobRecord,
    *,
    error: str | None,
    stage: str | None,
    issues: Sequence[dict[str, object]] = (),
    now: datetime | None = None,
) -> JobRecord:
    """Move a claimed job to ``finished/`` with its terminal status."""
    final = replace(
        job,
        status=JobStatus.SUCCEEDED if error is None else JobStatus.FAILED,
        stage=stage,
        error=error,
        issues=tuple(issues),
        updated_at=_now(now),
    )
    _move_job(root, final, FINISHED_DIR)
    return final


# Failure stage -> canonical issue category. Every stage maps to the layer
# that owns the failing work, so job issues reuse the frozen taxonomy
# instead of inventing a job-local one.
STAGE_ISSUE_CATEGORIES: dict[Stage, str] = {
    Stage.INGEST: "PHYSICAL_EXTRACTION",
    Stage.PHYSICAL: "PHYSICAL_EXTRACTION",
    Stage.EVIDENCE: "LAYOUT_REGION",
    Stage.LAYOUT: "LAYOUT_REGION",
    Stage.SEMANTIC: "SECTION_STRUCTURE",
    Stage.TRANSLATE: "TRANSLATION",
    Stage.RENDER: "RENDERING",
    Stage.INDEX: "RENDER_MAPPING",
}

_DEFAULT_ISSUE_CATEGORY = "PHYSICAL_EXTRACTION"


def job_failure_issue(
    *, error: BaseException, job_id: str, stage: Stage | None
) -> dict[str, object]:
    """Canonical Issue payload for a failed job (validates against ``Issue``).

    A stage-scoped failure is recoverable: the next attempt resumes from the
    stage state batch A recorded. A failure before any stage (unsupported
    input, unreadable source) reruns the same input and fails again, so it is
    FATAL with no fallback.
    """
    return {
        "id": str(uuid.uuid4()),
        "category": STAGE_ISSUE_CATEGORIES[stage] if stage is not None else _DEFAULT_ISSUE_CATEGORY,
        "severity": "ERROR" if stage is not None else "FATAL",
        "producer": f"pdf_pipeline.{stage.value}"
        if stage is not None
        else "pdf_pipeline.orchestrator",
        "message": str(error),
        "affectedIds": [job_id],
        "recoverable": stage is not None,
    }


Runner = Callable[[Path, Path, Path | None], dict[str, Path]]


def _default_runner(source: Path, workspace: Path, viewer_data_dir: Path | None) -> dict[str, Path]:
    # Imported here so a worker process starts without loading pdfium.
    from pdf_pipeline.pipeline import run_pipeline  # noqa: PLC0415

    return run_pipeline(source, workspace, viewer_data_dir=viewer_data_dir)


def heartbeat_path(root: Path) -> Path:
    """The liveness record for whichever worker serves ``root``."""
    return root / HEARTBEAT_NAME


def write_heartbeat(
    root: Path,
    *,
    started_at: str,
    concurrency: int,
    running: int,
    now: datetime | None = None,
) -> dict[str, object]:
    """Publish one liveness record atomically; the last writer wins."""
    payload: dict[str, object] = {
        "heartbeatVersion": HEARTBEAT_VERSION,
        "pid": os.getpid(),
        "startedAt": started_at,
        "updatedAt": _now(now),
        "concurrency": concurrency,
        "running": running,
    }
    _atomic_write_json(heartbeat_path(root), payload)
    return payload


def read_heartbeat(root: Path) -> dict[str, object] | None:
    """The current liveness record, or ``None`` when absent or malformed.

    A half-written or foreign file must read as "no worker", never as a
    worker with invented fields, so every key is type-checked rather than
    defaulted.
    """
    try:
        payload = json.loads(heartbeat_path(root).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    counts = ("pid", "concurrency", "running")
    stamps = ("heartbeatVersion", "startedAt", "updatedAt")
    if not all(key in payload for key in (*counts, *stamps)):
        return None
    if not all(
        isinstance(payload[key], int) and not isinstance(payload[key], bool) for key in counts
    ):
        return None
    if not all(isinstance(payload[key], str) for key in stamps):
        return None
    return payload


def clear_heartbeat(root: Path) -> None:
    """Drop the liveness record: no worker serves ``root`` any more."""
    heartbeat_path(root).unlink(missing_ok=True)


class JobWorker:
    """Polls the jobs root, claims work, and runs the pipeline to completion."""

    def __init__(
        self,
        root: Path,
        *,
        concurrency: int = 1,
        poll_interval: float = POLL_INTERVAL_S,
        runner: Runner | None = None,
    ) -> None:
        if concurrency < 1:
            raise ValueError("concurrency must be >= 1")
        self.root = root
        self.concurrency = concurrency
        self.poll_interval = poll_interval
        self._runner: Runner = runner or _default_runner
        self._started_at = _now(None)
        self._running = 0
        self._heartbeat_lock = threading.Lock()

    def recover(self) -> list[str]:
        return recover_running(self.root)

    def run_once(self) -> int:
        """Drain the currently queued jobs; returns how many ran.

        Beats once so even a ``--once`` run is observable while it works, and
        leaves no record behind: a root with no running worker must not read
        as live.
        """
        self._beat()
        try:
            return self._drain()
        finally:
            clear_heartbeat(self.root)

    def _drain(self) -> int:
        """Claim and run queued jobs until none are left."""
        executed = 0
        pending: dict[Future[JobRecord], JobClaim] = {}
        with ThreadPoolExecutor(max_workers=self.concurrency) as pool:
            try:
                while True:
                    # Claiming is bounded by concurrency: a claimed job holds
                    # its locks, so queueing more than we can run would block
                    # other workers (and other jobs of the same workspace)
                    # for no benefit.
                    while len(pending) < self.concurrency:
                        claim = claim_next(self.root)
                        if claim is None:
                            break
                        pending[pool.submit(self._execute, claim)] = claim
                    if not pending:
                        break
                    done, _ = wait(pending, return_when=FIRST_COMPLETED)
                    for future in done:
                        pending.pop(future)
                        future.result()
                        executed += 1
            finally:
                for future, claim in pending.items():
                    if future.cancel():
                        claim.release()
        return executed

    def run_forever(self, stop: threading.Event) -> None:
        """Recover orphaned jobs, then poll until ``stop`` is set.

        A daemon thread owns the liveness record for the whole run; the beat
        thread is joined before the record is cleared so a late beat cannot
        resurrect a file for a worker that already exited.
        """
        self.recover()
        self._beat()
        beats = threading.Thread(target=self._heartbeat_loop, args=(stop,), daemon=True)
        beats.start()
        try:
            while not stop.is_set():
                if self._drain() == 0:
                    stop.wait(self.poll_interval)
        finally:
            beats.join(timeout=HEARTBEAT_INTERVAL_S)
            clear_heartbeat(self.root)

    def _heartbeat_loop(self, stop: threading.Event) -> None:
        while not stop.wait(HEARTBEAT_INTERVAL_S):
            self._beat()

    def _beat(self) -> None:
        """Publish the liveness record; a failed beat never kills the worker."""
        with self._heartbeat_lock:
            running = self._running
        try:
            write_heartbeat(
                self.root,
                started_at=self._started_at,
                concurrency=self.concurrency,
                running=running,
            )
        except OSError:
            return

    def _execute(self, claim: JobClaim) -> JobRecord:
        # Imported at execution time: a claimed job means pdfium is about to
        # be needed anyway (the default runner imports the pipeline).
        from pdf_pipeline.pipeline import StageExecutionError  # noqa: PLC0415

        job = claim.job
        with self._heartbeat_lock:
            self._running += 1
        try:
            self._run_job(job)
        except StageExecutionError as error:
            return finish_job(
                self.root,
                job,
                error=str(error),
                stage=error.stage.value,
                issues=[job_failure_issue(error=error, job_id=job.id, stage=error.stage)],
            )
        except Exception as error:
            return finish_job(
                self.root,
                job,
                error=str(error),
                stage=None,
                issues=[job_failure_issue(error=error, job_id=job.id, stage=None)],
            )
        else:
            return finish_job(self.root, job, error=None, stage=None)
        finally:
            with self._heartbeat_lock:
                self._running -= 1
            claim.release()

    def _run_job(self, job: JobRecord) -> dict[str, Path]:
        viewer_data_dir = Path(job.viewer_data_dir) if job.viewer_data_dir else None
        return self._runner(Path(job.source), Path(job.workspace), viewer_data_dir)
