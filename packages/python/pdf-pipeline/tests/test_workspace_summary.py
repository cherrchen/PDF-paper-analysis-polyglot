# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false
"""Read-only workspace inspection (console `select` surface).

LaTeX compilation is faked exactly as in `test_rerender_workspace.py`, so the
summary and discovery helpers are exercised against a real committed workspace
without the toolchain. Both helpers must be pure reads: a listing that wrote a
manifest would silently adopt a workspace the caller only meant to describe.
"""

from __future__ import annotations

import os
from pathlib import Path

import pypdfium2 as pdfium
import pytest
from pdf_pipeline import pipeline
from pdf_pipeline.workspace import (
    MANIFEST_NAME,
    STAGE_ORDER,
    StageStatus,
    WorkspaceError,
    WorkspaceManager,
    discover_workspaces,
    summarize_workspace,
)


def _fake_compile(tex: Path, build_dir: Path) -> Path:
    del tex
    build_dir.mkdir(parents=True, exist_ok=True)
    out = build_dir / "target.pdf"
    doc = pdfium.PdfDocument.new()
    doc.new_page(612, 792)
    doc.save(out)
    doc.close()
    return out


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A workspace committed by run_pipeline on the smoke fixture."""
    fixture = Path(__file__).resolve().parents[4] / "tests/fixtures/source/latex/build/smoke.pdf"
    if not fixture.exists():
        pytest.skip("smoke fixture PDF not built; run `just latex-smoke`")
    monkeypatch.setattr(pipeline, "compile_latex", _fake_compile)
    out = tmp_path / "ws"
    pipeline.run_pipeline(fixture, out)
    return out


def test_summary_of_a_committed_workspace(workspace: Path) -> None:
    before = (workspace / MANIFEST_NAME).read_bytes()

    summary = summarize_workspace(workspace)

    assert summary.error is None
    assert summary.complete is True
    assert summary.workspace_version == "0.1.0"
    assert summary.name == "ws"
    assert summary.path == str(workspace)
    assert sorted(summary.stages) == sorted(stage.value for stage in STAGE_ORDER)
    assert set(summary.stages.values()) == {StageStatus.COMPLETED.value}
    assert summary.updated_at.endswith("+00:00")
    # Summarizing is a read: it must not adopt or rewrite the manifest.
    assert (workspace / MANIFEST_NAME).read_bytes() == before


def test_summary_degrades_on_a_directory_without_a_manifest(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()

    summary = summarize_workspace(empty)

    assert summary.error is not None
    assert "missing workspace manifest" in summary.error
    assert summary.complete is False
    assert summary.workspace_version == ""
    assert summary.updated_at == ""
    assert sorted(summary.stages) == sorted(stage.value for stage in STAGE_ORDER)
    assert set(summary.stages.values()) == {StageStatus.PENDING.value}
    assert summary.to_json()["name"] == "empty"


def test_summary_reports_a_removed_artifact_not_a_rewritten_record(workspace: Path) -> None:
    (workspace / "target.pdf").unlink()

    summary = summarize_workspace(workspace)

    assert summary.error is None
    assert summary.complete is False
    # The record still says the stage committed; only the artifacts decide
    # whether the committed output is still readable.
    assert summary.stages["render"] == StageStatus.COMPLETED.value


def test_summary_refuses_a_workspace_bound_to_another_source(workspace: Path) -> None:
    (workspace / "source.pdf").write_bytes(b"%PDF-1.4\nnot the committed source\n")

    summary = summarize_workspace(workspace)

    assert summary.error is not None
    assert "different source PDF" in summary.error
    assert summary.complete is False


def test_load_never_creates_a_manifest(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    root.mkdir()

    with pytest.raises(WorkspaceError, match="missing workspace manifest"):
        WorkspaceManager(root).load()

    assert not (root / MANIFEST_NAME).exists()


def test_discover_workspaces_merges_jobs_root_and_extra(tmp_path: Path, workspace: Path) -> None:
    jobs_root = tmp_path / "jobs"
    nested = jobs_root / "workspaces" / "other"
    nested.mkdir(parents=True)
    (nested / MANIFEST_NAME).write_text("{}", encoding="utf-8")
    (jobs_root / "workspaces" / "not-a-workspace").mkdir()

    found = discover_workspaces(jobs_root=jobs_root, extra=(workspace, workspace))

    # The deduplicated set holds both, and the manifest-less directory is not a
    # workspace. The API's own workspace is normally outside the jobs root.
    assert len(found) == 2
    assert {path.resolve() for path in found} == {nested.resolve(), workspace.resolve()}


def test_discover_workspaces_orders_newest_first(tmp_path: Path, workspace: Path) -> None:
    jobs_root = tmp_path / "jobs"
    stale = jobs_root / "workspaces" / "stale"
    stale.mkdir(parents=True)
    manifest = stale / MANIFEST_NAME
    manifest.write_text("{}", encoding="utf-8")
    os.utime(manifest, (1, 1))

    found = discover_workspaces(jobs_root=jobs_root, extra=(workspace,))

    assert [path.name for path in found] == ["ws", "stale"]
