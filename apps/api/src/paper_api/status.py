"""Console status endpoint: ``GET /api/status`` (process, worker, queue, viewer).

Kept out of ``__main__`` so the HTTP layer stays a thin adapter and the
payload is directly testable. ``pdf_pipeline.jobs`` is imported lazily inside
the handler so the API process keeps its sub-second startup without pulling
pdfium.

The worker is observed through the heartbeat file it writes into the jobs
root — there is no cross-process handle to ask. A heartbeat older than
``HEARTBEAT_STALE_S`` counts as a dead worker; no heartbeat at all means
``present`` false, i.e. no worker is running rather than "no worker ever ran".
Nothing here writes: this module only reports.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast

from paper_api import health

if TYPE_CHECKING:
    from pathlib import Path

STATUS_PATH = "/api/status"

# A heartbeat's absence is reported with every key present but null, so the
# consumer (and the status panel) never has to branch on missing keys.
_ABSENT_WORKER: dict[str, object] = {
    "present": False,
    "alive": False,
    "pid": None,
    "startedAt": None,
    "updatedAt": None,
    "ageSeconds": None,
    "concurrency": None,
    "running": 0,
}


def _worker_status(jobs_root: Path) -> dict[str, object]:
    """The worker's last heartbeat, aged against ``HEARTBEAT_STALE_S``.

    A heartbeat whose ``updatedAt`` is unparsable is reported as absent: an
    unreadable timestamp is not evidence that a worker is alive, and a status
    probe must never raise over a file it cannot read.
    """
    from pdf_pipeline.jobs import HEARTBEAT_STALE_S, read_heartbeat  # noqa: PLC0415

    heartbeat = read_heartbeat(jobs_root)
    if heartbeat is None:
        return dict(_ABSENT_WORKER)
    updated_at = heartbeat.get("updatedAt")
    try:
        age_seconds = round(
            (datetime.now(UTC) - datetime.fromisoformat(cast("str", updated_at))).total_seconds(),
            1,
        )
    except (TypeError, ValueError):
        return dict(_ABSENT_WORKER)
    return {
        "present": True,
        "alive": age_seconds <= HEARTBEAT_STALE_S,
        "pid": heartbeat.get("pid"),
        "startedAt": heartbeat.get("startedAt"),
        "updatedAt": updated_at,
        "ageSeconds": age_seconds,
        "concurrency": heartbeat.get("concurrency"),
        "running": heartbeat.get("running"),
    }


def _job_counts(jobs_root: Path) -> dict[str, object]:
    """Queue depth by status, plus the oldest queued timestamp."""
    from pdf_pipeline.jobs import list_jobs  # noqa: PLC0415

    counts: dict[str, int] = {"queued": 0, "running": 0, "succeeded": 0, "failed": 0}
    oldest_queued_at: str | None = None
    for record in list_jobs(jobs_root):
        status = record.status.value
        if status in counts:
            counts[status] += 1
        if status == "queued" and (
            oldest_queued_at is None or record.created_at < oldest_queued_at
        ):
            oldest_queued_at = record.created_at
    return {**counts, "oldestQueuedAt": oldest_queued_at}


def _viewer_status(data_dir: Path) -> dict[str, object] | None:
    """The published revision and its workspace, or ``None`` when unpublished."""
    try:
        raw: object = json.loads((data_dir / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict):
        return None
    manifest = cast("dict[str, object]", raw)
    revision = manifest.get("revision")
    workspace = manifest.get("workspace")
    return {
        "revision": revision if isinstance(revision, str) and revision else None,
        "workspace": workspace if isinstance(workspace, str) and workspace else None,
    }


def handle_status(*, jobs_root: Path, data_dir: Path) -> tuple[int, dict[str, object]]:
    """Report API, worker, queue and publication status; always 200.

    Reported problems are payload facts (``alive`` false, a null ``viewer``),
    never HTTP failures: a status probe that itself errors cannot explain why.
    """
    return 200, {
        "ok": True,
        "api": health(),
        "worker": _worker_status(jobs_root),
        "jobs": _job_counts(jobs_root),
        "viewer": _viewer_status(data_dir),
    }
