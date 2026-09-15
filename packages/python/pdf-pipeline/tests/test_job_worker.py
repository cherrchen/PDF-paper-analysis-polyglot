# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportPrivateUsage=false
"""Worker execution tests: claim, run, attribute failure, resume (M8 batch B).

LaTeX compilation is faked (empty PDFium pages) so the worker drives the real
pipeline against the smoke fixture: a job runs to completion, a stage failure
becomes a canonical issue and a retry resumes from the batch A stage state,
and a killed worker's job is recovered from its released ``flock``.
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

import pypdfium2 as pdfium
import pytest
from pdf_pipeline import pipeline
from pdf_pipeline.jobs import (
    JobStatus,
    JobWorker,
    create_job,
    get_job,
    recover_running,
    retry_job,
)
from pdf_pipeline.workspace import MANIFEST_NAME, STAGE_ORDER

if TYPE_CHECKING:
    from collections.abc import Callable

_RUNNERS = (
    "_run_ingest_stage",
    "_run_physical_stage",
    "_run_evidence_stage",
    "_run_layout_stage",
    "_run_semantic_stage",
    "_run_translation_stage",
    "_run_render_stage",
    "_run_index_stage",
)


def _fake_compile(tex: Path, build_dir: Path) -> Path:
    del tex
    build_dir.mkdir(parents=True, exist_ok=True)
    out = build_dir / "target.pdf"
    doc = pdfium.PdfDocument.new()
    doc.new_page(612, 792)
    doc.new_page(612, 792)
    doc.save(out)
    doc.close()
    return out


@pytest.fixture
def smoke_pdf() -> Path:
    fixture = Path(__file__).resolve().parents[4] / "tests/fixtures/source/latex/build/smoke.pdf"
    if not fixture.exists():
        pytest.skip("smoke fixture PDF not built; run `just latex-smoke`")
    return fixture


@pytest.fixture
def fake_latex(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pipeline, "compile_latex", _fake_compile)


def _count_stage_runs(monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    """Wrap every stage runner with a call counter (runs are still real)."""
    counts: dict[str, int] = dict.fromkeys(_RUNNERS, 0)
    for name in _RUNNERS:
        original: Callable[..., object] = getattr(pipeline, name)

        def wrapper(
            *args: object,
            _name: str = name,
            _fn: Callable[..., object] = original,
            **kwargs: object,
        ) -> object:
            counts[_name] += 1
            return _fn(*args, **kwargs)

        monkeypatch.setattr(pipeline, name, wrapper)
    return counts


def test_worker_runs_job_end_to_end(tmp_path: Path, smoke_pdf: Path, fake_latex: None) -> None:
    root = tmp_path / "jobs"
    workspace = tmp_path / "ws"
    record = create_job(root, source=smoke_pdf, workspace=workspace)

    assert JobWorker(root).run_once() == 1

    stored = get_job(root, record.id)
    assert stored.status is JobStatus.SUCCEEDED
    assert stored.stage is None
    assert stored.error is None
    manifest = json.loads((workspace / MANIFEST_NAME).read_text(encoding="utf-8"))
    assert set(manifest["stages"]) == {stage.value for stage in STAGE_ORDER}
    assert {record["status"] for record in manifest["stages"].values()} == {"completed"}
    assert (workspace / "target.pdf").is_file()


def test_stage_failure_writes_issue_and_retry_resumes(
    tmp_path: Path, smoke_pdf: Path, fake_latex: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    counts = _count_stage_runs(monkeypatch)
    healthy_semantic = pipeline._run_semantic_stage

    def crash(*args: object, **kwargs: object) -> object:
        raise RuntimeError("boom")

    monkeypatch.setattr(pipeline, "_run_semantic_stage", crash)
    root = tmp_path / "jobs"
    record = create_job(root, source=smoke_pdf, workspace=tmp_path / "ws")

    assert JobWorker(root).run_once() == 1

    failed = get_job(root, record.id)
    assert failed.status is JobStatus.FAILED
    assert failed.stage == "semantic"
    assert len(failed.issues) == 1
    issue = failed.issues[0]
    assert issue["severity"] == "ERROR"
    assert issue["category"] == "SECTION_STRUCTURE"
    assert issue["producer"] == "pdf_pipeline.semantic"
    assert issue["recoverable"] is True
    assert counts["_run_physical_stage"] == 1
    assert counts["_run_layout_stage"] == 1

    monkeypatch.setattr(pipeline, "_run_semantic_stage", healthy_semantic)
    requeued = retry_job(root, record.id)
    assert requeued.status is JobStatus.QUEUED
    assert requeued.attempt == 2

    assert JobWorker(root).run_once() == 1

    final = get_job(root, record.id)
    assert final.status is JobStatus.SUCCEEDED
    assert final.stage is None
    # Resume evidence: the retry reran SEMANTIC and its downstream only.
    assert counts["_run_ingest_stage"] == 1
    assert counts["_run_physical_stage"] == 1
    assert counts["_run_evidence_stage"] == 1
    assert counts["_run_layout_stage"] == 1
    assert counts["_run_semantic_stage"] == 1


def test_pre_stage_failure_is_fatal_and_not_recoverable(tmp_path: Path, smoke_pdf: Path) -> None:
    def runner(source: Path, workspace: Path, viewer_data_dir: Path | None) -> dict[str, Path]:
        del source, workspace, viewer_data_dir
        raise ValueError("unsupported input PDF: scanned pages")

    root = tmp_path / "jobs"
    record = create_job(root, source=smoke_pdf, workspace=tmp_path / "ws")

    assert JobWorker(root, runner=runner).run_once() == 1

    stored = get_job(root, record.id)
    assert stored.status is JobStatus.FAILED
    assert stored.stage is None
    assert stored.error is not None
    assert "unsupported input PDF" in stored.error
    assert len(stored.issues) == 1
    assert stored.issues[0]["severity"] == "FATAL"
    assert stored.issues[0]["recoverable"] is False


def test_worker_passes_record_viewer_data_dir_to_runner(tmp_path: Path, smoke_pdf: Path) -> None:
    """The job-published revision must land in the dir the record names (batch F)."""
    seen: list[tuple[Path, Path, Path | None]] = []

    def runner(source: Path, workspace: Path, viewer_data_dir: Path | None) -> dict[str, Path]:
        seen.append((source, workspace, viewer_data_dir))
        return {}

    root = tmp_path / "jobs"
    viewer = tmp_path / "viewer-data"
    record = create_job(root, source=smoke_pdf, workspace=tmp_path / "ws", viewer_data_dir=viewer)

    assert JobWorker(root, runner=runner).run_once() == 1

    assert get_job(root, record.id).status is JobStatus.SUCCEEDED
    assert seen == [(smoke_pdf, tmp_path / "ws", viewer)]


@pytest.mark.parametrize("same_workspace", [True, False])
def test_concurrency_respects_workspace_lock(
    tmp_path: Path, smoke_pdf: Path, same_workspace: bool
) -> None:
    root = tmp_path / "jobs"
    shared = tmp_path / "ws-shared"
    records = [
        create_job(root, source=smoke_pdf, workspace=shared),
        create_job(
            root,
            source=smoke_pdf,
            workspace=shared if same_workspace else tmp_path / "ws-other",
        ),
    ]
    guard = threading.Lock()
    state = {"active": 0, "peak": 0}

    def runner(source: Path, workspace: Path, viewer_data_dir: Path | None) -> dict[str, Path]:
        del source, workspace, viewer_data_dir
        with guard:
            state["active"] += 1
            state["peak"] = max(state["peak"], state["active"])
        time.sleep(0.2)
        with guard:
            state["active"] -= 1
        return {}

    assert JobWorker(root, concurrency=2, runner=runner).run_once() == 2

    assert state["peak"] == (1 if same_workspace else 2)
    for record in records:
        assert get_job(root, record.id).status is JobStatus.SUCCEEDED


_CLAIM_AND_DIE = """
import os
import sys
from pathlib import Path

from pdf_pipeline.jobs import claim_next

claim = claim_next(Path(sys.argv[1]))
if claim is None:
    raise SystemExit("nothing to claim")
os._exit(0)
"""


def test_recover_running_after_worker_death(
    tmp_path: Path, smoke_pdf: Path, fake_latex: None
) -> None:
    root = tmp_path / "jobs"
    workspace = tmp_path / "ws"
    record = create_job(root, source=smoke_pdf, workspace=workspace)

    # A worker that claims the job and dies: the kernel drops its flock.
    subprocess.run([sys.executable, "-c", _CLAIM_AND_DIE, str(root)], check=True)  # noqa: S603

    assert (root / "running" / f"{record.id}.json").is_file()
    assert recover_running(root) == [record.id]
    assert get_job(root, record.id).status is JobStatus.QUEUED

    assert JobWorker(root).run_once() == 1
    assert get_job(root, record.id).status is JobStatus.SUCCEEDED
    assert (workspace / "target.pdf").is_file()
