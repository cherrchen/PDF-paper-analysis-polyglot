# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportPrivateUsage=false
"""Resume tests for the staged pipeline workspace (M8 batch A).

LaTeX compilation is faked (empty PDFium pages) so the tests exercise the
stage driver against a real smoke-fixture PDF: interruption preserves
completed stage artifacts, restart reruns only unfinished stages, and a
half-written or tampered artifact set is never accepted as success.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pypdfium2 as pdfium
import pytest
from paper_llm.config import load_translation_config
from pdf_pipeline import pipeline
from pdf_pipeline.workspace import (
    MANIFEST_NAME,
    STAGE_ORDER,
    Stage,
    WorkspaceManager,
    WorkspaceSourceMismatchError,
)

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

_ARTIFACTS = (
    "physical.json",
    "evidence.json",
    "evidence-bundles.json",
    "probe.json",
    "layout.json",
    "semantic.json",
    "resources.json",
    "translation.json",
    "render.json",
    "mapping.json",
    "source.pdf",
    "target.pdf",
    MANIFEST_NAME,
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
def workspace(smoke_pdf: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(pipeline, "compile_latex", _fake_compile)
    out = tmp_path / "ws"
    pipeline.run_pipeline(smoke_pdf, out)
    return out


def _count_stage_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, int]:
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


def _snapshot(workspace: Path) -> dict[str, bytes]:
    return {name: (workspace / name).read_bytes() for name in _ARTIFACTS}


def test_full_rerun_skips_every_stage(
    workspace: Path, smoke_pdf: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(pipeline, "compile_latex", _fake_compile)
    before = _snapshot(workspace)
    counts = _count_stage_runs(monkeypatch)

    pipeline.run_pipeline(smoke_pdf, tmp_path / "ws")

    assert all(count == 0 for count in counts.values()), counts
    assert _snapshot(workspace) == before


def test_interrupted_run_resumes_from_stage_state(
    workspace: Path, smoke_pdf: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A fresh workspace whose TRANSLATE stage crashes mid-run.
    out = tmp_path / "crash"
    monkeypatch.setattr(pipeline, "compile_latex", _fake_compile)
    original_translate: Callable[..., object] = pipeline._run_translation_stage

    def crash(*args: object, **kwargs: object) -> object:
        raise RuntimeError("simulated worker kill")

    monkeypatch.setattr(pipeline, "_run_translation_stage", crash)
    with pytest.raises(RuntimeError, match="simulated worker kill"):
        pipeline.run_pipeline(smoke_pdf, out)

    # Stages before TRANSLATE are committed with their artifacts on disk.
    manifest = json.loads((out / MANIFEST_NAME).read_text())
    assert set(manifest["stages"]) == {"ingest", "physical", "evidence", "layout", "semantic"}
    for name in ("physical.json", "layout.json", "semantic.json", "source.pdf"):
        assert (out / name).is_file()
    assert not (out / "translation.json").exists()
    # Half-written stages are not marked complete.
    manager = WorkspaceManager(out)
    manager.open_or_create(smoke_pdf.read_bytes())
    assert not manager.stage_completed(Stage.TRANSLATE)

    # Restart: only TRANSLATE and its downstream rerun.
    monkeypatch.setattr(pipeline, "_run_translation_stage", original_translate)
    counts = _count_stage_runs(monkeypatch)
    pipeline.run_pipeline(smoke_pdf, out)
    assert counts["_run_ingest_stage"] == 0
    assert counts["_run_physical_stage"] == 0
    assert counts["_run_evidence_stage"] == 0
    assert counts["_run_layout_stage"] == 0
    assert counts["_run_semantic_stage"] == 0
    assert counts["_run_translation_stage"] == 1
    assert counts["_run_render_stage"] == 1
    assert counts["_run_index_stage"] == 1
    for name in _ARTIFACTS:
        assert (out / name).is_file(), name
    assert not (out / ".staging").exists()


def test_tampered_artifact_reruns_its_stage(
    workspace: Path, smoke_pdf: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(pipeline, "compile_latex", _fake_compile)
    before = _snapshot(workspace)
    (tmp_path / "ws" / "layout.json").write_bytes(b"corrupted")

    counts = _count_stage_runs(monkeypatch)
    pipeline.run_pipeline(smoke_pdf, tmp_path / "ws")

    assert counts["_run_layout_stage"] == 1
    assert counts["_run_semantic_stage"] == 0, "deterministic rerun reproduces the same bytes"
    assert all(counts[runner] == 0 for runner in _RUNNERS if runner != "_run_layout_stage")
    assert _snapshot(workspace) == before


def test_stage_records_follow_m8_order(workspace: Path) -> None:
    manifest = json.loads((workspace / MANIFEST_NAME).read_text())
    committed = list(manifest["stages"])
    assert committed == [stage.value for stage in STAGE_ORDER]
    for record in manifest["stages"].values():
        assert record["status"] == "completed"
        assert record["producerVersion"]
        assert record["inputFingerprint"]
        assert record["artifacts"]


def test_resume_index_uses_committed_pdf(
    workspace: Path, smoke_pdf: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import shutil

    shutil.rmtree(workspace / "build")
    (workspace / "mapping.json").unlink()
    counts = _count_stage_runs(monkeypatch)
    pipeline.run_pipeline(smoke_pdf, workspace)
    assert counts["_run_render_stage"] == 0
    assert counts["_run_index_stage"] == 1


def test_producer_upgrade_reruns_stage(
    workspace: Path, smoke_pdf: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(pipeline.STAGE_PRODUCER_VERSIONS, Stage.LAYOUT, "new-version")
    counts = _count_stage_runs(monkeypatch)
    pipeline.run_pipeline(smoke_pdf, workspace)
    assert counts["_run_layout_stage"] == 1
    assert counts["_run_physical_stage"] == 0


@pytest.mark.parametrize("new_destination", [False, True])
def test_resume_repairs_viewer_publication(
    workspace: Path,
    smoke_pdf: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    new_destination: bool,
) -> None:
    data_dir = tmp_path / "new-viewer" if new_destination else workspace / "viewer/data"
    if not new_destination:
        (data_dir / "target.pdf").write_bytes(b"corrupt")
    counts = _count_stage_runs(monkeypatch)
    pipeline.run_pipeline(smoke_pdf, workspace, viewer_data_dir=data_dir)
    assert counts["_run_index_stage"] == 1
    assert counts["_run_render_stage"] == 0
    assert (data_dir / "target.pdf").read_bytes() == (workspace / "target.pdf").read_bytes()


def test_rerender_survives_pipeline_resume(
    workspace: Path, smoke_pdf: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    translation = json.loads((workspace / "translation.json").read_text())
    node_id = translation["entries"][0]["semanticNodeId"]
    pipeline.rerender_workspace(
        workspace,
        viewer_data_dir=workspace / "viewer/data",
        node_ids={node_id},
    )
    before = (workspace / "translation.json").read_bytes()
    counts = _count_stage_runs(monkeypatch)
    pipeline.run_pipeline(smoke_pdf, workspace)
    assert counts["_run_translation_stage"] == 0
    assert counts["_run_render_stage"] == 0
    assert (workspace / "translation.json").read_bytes() == before
    assert (workspace / "viewer/data/target.pdf").read_bytes() == (
        workspace / "target.pdf"
    ).read_bytes()


def _manifest_records(workspace: Path) -> dict[str, dict[str, object]]:
    stages = json.loads((workspace / MANIFEST_NAME).read_text())["stages"]
    return cast("dict[str, dict[str, object]]", stages)


def test_registry_change_reruns_evidence_and_layout(
    workspace: Path, smoke_pdf: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(pipeline, "registry_fingerprint", lambda: "changed-registry")
    counts = _count_stage_runs(monkeypatch)

    pipeline.run_pipeline(smoke_pdf, workspace)

    assert counts["_run_evidence_stage"] == 1
    assert counts["_run_layout_stage"] == 1
    assert counts["_run_ingest_stage"] == 0
    assert counts["_run_physical_stage"] == 0
    assert counts["_run_semantic_stage"] == 0
    # Identical output bytes, so the tail is still current.
    assert counts["_run_translation_stage"] == 0


def test_parser_dump_change_reruns_evidence(
    smoke_pdf: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(pipeline, "compile_latex", _fake_compile)
    dump = tmp_path / "mineru.json"
    dump.write_text("{}")
    monkeypatch.setenv("MINERU_DUMP", str(dump))
    out = tmp_path / "ws"
    pipeline.run_pipeline(smoke_pdf, out)

    # Freshness is judged against the same stage config the run used.
    manager = WorkspaceManager(
        out,
        stage_configs=pipeline.stage_config_inputs(
            load_translation_config(), smoke_pdf.read_bytes()
        ),
    )
    manager.open_or_create(smoke_pdf.read_bytes())
    assert manager.stage_completed(Stage.EVIDENCE)

    dump.write_text('{"pdf_info": []}')
    counts = _count_stage_runs(monkeypatch)
    pipeline.run_pipeline(smoke_pdf, out)

    assert counts["_run_evidence_stage"] == 1
    assert counts["_run_ingest_stage"] == 0
    assert counts["_run_physical_stage"] == 0
    # LAYOUT keys on the registry, not on parser dumps.
    assert counts["_run_layout_stage"] == 0
    assert counts["_run_semantic_stage"] == 0


def test_live_parser_env_change_reruns_evidence(
    workspace: Path, smoke_pdf: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DOCLING_CMD", "docling --json")
    counts = _count_stage_runs(monkeypatch)

    pipeline.run_pipeline(smoke_pdf, workspace)

    assert counts["_run_evidence_stage"] == 1
    assert counts["_run_ingest_stage"] == 0
    assert counts["_run_physical_stage"] == 0
    assert counts["_run_layout_stage"] == 0
    assert counts["_run_semantic_stage"] == 0


def test_translation_config_change_reruns_translate(
    workspace: Path, smoke_pdf: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert json.loads((workspace / "translation.json").read_text())["targetLocale"] == "zh-CN"
    monkeypatch.setenv("PAPER_TARGET_LOCALE", "ja-JP")
    counts = _count_stage_runs(monkeypatch)

    pipeline.run_pipeline(smoke_pdf, workspace)

    assert counts["_run_translation_stage"] == 1
    assert counts["_run_semantic_stage"] == 0
    assert counts["_run_physical_stage"] == 0
    assert counts["_run_evidence_stage"] == 0
    assert json.loads((workspace / "translation.json").read_text())["targetLocale"] == "ja-JP"


def test_rerun_from_stage_reruns_only_tail(
    workspace: Path, smoke_pdf: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = _manifest_records(workspace)
    counts = _count_stage_runs(monkeypatch)

    pipeline.run_pipeline(smoke_pdf, workspace, rerun_from=Stage.TRANSLATE)

    for runner in _RUNNERS[: _RUNNERS.index("_run_translation_stage")]:
        assert counts[runner] == 0, runner
    assert counts["_run_translation_stage"] == 1
    assert counts["_run_render_stage"] == 1
    assert counts["_run_index_stage"] == 1
    after = _manifest_records(workspace)
    for stage in ("ingest", "physical", "evidence", "layout", "semantic"):
        assert after[stage] == before[stage], stage


def test_source_change_requires_accept_flag(
    workspace: Path, smoke_pdf: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    other = (
        Path(__file__).resolve().parents[4] / "tests/fixtures/source/latex/build/figure-caption.pdf"
    )
    if not other.exists():
        pytest.skip("second fixture PDF not built; run `just latex-smoke`")
    with pytest.raises(WorkspaceSourceMismatchError):
        pipeline.run_pipeline(other, workspace)
    assert (workspace / "source.pdf").read_bytes() == smoke_pdf.read_bytes()

    counts = _count_stage_runs(monkeypatch)
    pipeline.run_pipeline(other, workspace, accept_source_change=True)

    assert all(counts[runner] == 1 for runner in _RUNNERS), counts
    assert (workspace / "source.pdf").read_bytes() == other.read_bytes()
    records = _manifest_records(workspace)
    assert set(records) == {stage.value for stage in STAGE_ORDER}


def test_rerender_records_match_stage_configs(
    workspace: Path, smoke_pdf: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    translation = json.loads((workspace / "translation.json").read_text())
    node_id = translation["entries"][0]["semanticNodeId"]
    pipeline.rerender_workspace(
        workspace,
        viewer_data_dir=workspace / "viewer/data",
        node_ids={node_id},
    )
    counts = _count_stage_runs(monkeypatch)

    pipeline.run_pipeline(smoke_pdf, workspace)

    # rerender rebuilds translation/render cleanly, so no stage up to RENDER
    # reruns; INDEX was deliberately invalidated by the viewer republication.
    assert all(counts[runner] == 0 for runner in _RUNNERS if runner != "_run_index_stage"), counts
    assert counts["_run_index_stage"] == 1


def test_semantic_stage_drops_stale_resource_files(
    workspace: Path, smoke_pdf: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stale = workspace / "resources" / "stale.png"
    stale.parent.mkdir(exist_ok=True)
    stale.write_bytes(b"stale raster from an earlier run")

    counts = _count_stage_runs(monkeypatch)
    pipeline.run_pipeline(smoke_pdf, workspace, rerun_from=Stage.SEMANTIC)

    assert counts["_run_semantic_stage"] == 1
    assert not stale.exists()
    artifacts = cast("dict[str, str]", _manifest_records(workspace)["semantic"]["artifacts"])
    assert "resources/stale.png" not in artifacts
