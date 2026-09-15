"""Job endpoints business logic: submit, list, inspect, retry (M8 batch B).

Kept out of ``__main__`` so the HTTP layer stays a thin adapter and every
handler is directly testable. ``pdf_pipeline.jobs`` is imported lazily inside
each handler so the API process keeps its sub-second startup without pulling
pdfium.

Submission takes explicit absolute paths (``source``, ``workspace``,
optional ``viewerDataDir``) rather than a Project concept: batches B-F add
grouping above the job record, not inside it.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

JOBS_PREFIX = "/api/jobs"

_JOB_ID_PATTERN = re.compile(r"[0-9a-f]{32}")


def _json_object(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise TypeError("expected JSON object")
    typed: dict[str, object] = {}
    for key, item in value.items():  # pyright: ignore[reportUnknownVariableType, reportUnknownMemberType]
        typed[str(key)] = item  # pyright: ignore[reportUnknownArgumentType]
    return typed


def _required_path(payload: dict[str, object], key: str) -> Path:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise TypeError(f"{key} must be a non-empty string")
    return Path(value)


def parse_job_request(raw: bytes) -> tuple[Path, Path, Path | None]:
    """Extract (source, workspace, viewerDataDir) from a POST body.

    ``TypeError`` marks a well-shaped JSON body with wrong field types;
    ``ValueError`` marks a relative path. Malformed JSON and undecodable
    bytes raise ``json.JSONDecodeError`` / ``UnicodeDecodeError``, which are
    both ``ValueError`` subclasses.
    """
    payload = _json_object(json.loads(raw.decode("utf-8")))
    source = _required_path(payload, "source")
    workspace = _required_path(payload, "workspace")
    viewer_data_dir: Path | None = None
    raw_viewer = payload.get("viewerDataDir")
    if raw_viewer is not None:
        if not isinstance(raw_viewer, str) or not raw_viewer:
            raise TypeError("viewerDataDir must be a non-empty string or null")
        viewer_data_dir = Path(raw_viewer)
    for path in (source, workspace, viewer_data_dir):
        if path is not None and not path.is_absolute():
            raise ValueError("paths must be absolute")
    return source, workspace, viewer_data_dir


def handle_submit_job(
    raw_body: bytes,
    *,
    jobs_root: Path,
    default_viewer_data_dir: Path | None = None,
) -> tuple[int, dict[str, object]]:
    """Queue a job; returns (http_status, json_payload).

    An omitted (or null) ``viewerDataDir`` falls back to
    ``default_viewer_data_dir`` — the server's own ``--data-dir`` — so a
    browser-submitted job publishes into the directory the viewer reads.
    Explicit values are still validated by ``parse_job_request``.
    """
    try:
        source, workspace, viewer_data_dir = parse_job_request(raw_body)
    except (ValueError, TypeError, UnicodeDecodeError) as error:
        return 400, {"ok": False, "error": str(error)}
    if not source.is_file():
        return 400, {"ok": False, "error": f"source PDF not found: {source}"}
    viewer_data_dir = viewer_data_dir or default_viewer_data_dir
    try:
        from pdf_pipeline.jobs import create_job  # noqa: PLC0415

        record = create_job(
            jobs_root,
            source=source,
            workspace=workspace,
            viewer_data_dir=viewer_data_dir,
        )
    except Exception as error:
        return 500, {"ok": False, "error": str(error)}
    return 202, {"ok": True, "job": record.to_json()}


def handle_list_jobs(*, jobs_root: Path) -> tuple[int, dict[str, object]]:
    """Every known job, oldest first."""
    from pdf_pipeline.jobs import list_jobs  # noqa: PLC0415

    return 200, {"ok": True, "jobs": [record.to_json() for record in list_jobs(jobs_root)]}


def handle_get_job(job_id: str, *, jobs_root: Path) -> tuple[int, dict[str, object]]:
    """One job record, or 404 when unknown."""
    from pdf_pipeline.jobs import JobNotFoundError, get_job  # noqa: PLC0415

    try:
        record = get_job(jobs_root, job_id)
    except JobNotFoundError:
        return 404, {"ok": False, "error": f"unknown job: {job_id}"}
    return 200, {"ok": True, "job": record.to_json()}


def handle_retry_job(job_id: str, *, jobs_root: Path) -> tuple[int, dict[str, object]]:
    """Requeue a failed job; 409 when the job is not in a retryable state."""
    from pdf_pipeline.jobs import JobNotFoundError, JobStateError, retry_job  # noqa: PLC0415

    try:
        record = retry_job(jobs_root, job_id)
    except JobNotFoundError:
        return 404, {"ok": False, "error": f"unknown job: {job_id}"}
    except JobStateError as error:
        return 409, {"ok": False, "error": str(error)}
    return 202, {"ok": True, "job": record.to_json()}


def job_id_from_path(path: str, *, suffix: str = "") -> str | None:
    """Job id from ``/api/jobs/<id>`` (or ``/api/jobs/<id>/retry``)."""
    prefix = JOBS_PREFIX + "/"
    if not path.startswith(prefix) or not path.endswith(suffix):
        return None
    candidate = path[len(prefix) : len(path) - len(suffix)]
    if _JOB_ID_PATTERN.fullmatch(candidate) is None:
        return None
    return candidate


def match_jobs_path(path: str) -> tuple[str, str | None] | None:
    """Classify a request path as a jobs route: collection, item, or retry."""
    if path == JOBS_PREFIX:
        return "collection", None
    retry_id = job_id_from_path(path, suffix="/retry")
    if retry_id is not None:
        return "retry", retry_id
    item_id = job_id_from_path(path)
    if item_id is not None:
        return "item", item_id
    return None
