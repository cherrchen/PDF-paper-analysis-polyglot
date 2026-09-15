# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportPrivateUsage=false
"""End-to-end evidence-specialist failure isolation (M8 batch D).

A specialist that cannot run must degrade one capability, never the
document: the run keeps a TABLE line-row fallback (or the internal
front-matter heuristics), records one ERROR Issue attributed to the
failing provider, commits EVIDENCE as ``degraded`` so the next run retries
it, and lets every downstream stage proceed. LaTeX compilation is faked
(empty PDFium pages) so the tests exercise the real stage driver without a
TeX toolchain.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pypdfium2 as pdfium
import pytest
from paper_llm.config import load_translation_config
from pdf_pipeline import pipeline
from pdf_pipeline.capabilities import Capability, load_registry
from pdf_pipeline.pipeline import stage_config_inputs
from pdf_pipeline.workspace import Stage, StageStatus, WorkspaceManager

if TYPE_CHECKING:
    from collections.abc import Callable

FIXTURE_DIR = Path(__file__).resolve().parents[4] / "tests/fixtures/source/latex/build"


def _fake_compile(tex: Path, build_dir: Path) -> Path:
    del tex
    build_dir.mkdir(parents=True, exist_ok=True)
    out = build_dir / "target.pdf"
    doc = pdfium.PdfDocument.new()
    doc.new_page(612, 792)
    doc.save(out)
    doc.close()
    return out


def _fixture(name: str) -> Path:
    path = FIXTURE_DIR / f"{name}.pdf"
    if not path.exists():
        pytest.skip(f"fixture PDF {name} not built; run `just latex-smoke`")
    return path


def _overlay(capability: str, **changes: str) -> dict[str, Capability]:
    """Overlay one capability slot on top of the bundled registry."""
    overlay = dict(load_registry())
    slot = overlay[capability]
    overlay[capability] = Capability(
        name=slot.name,
        primary=changes.get("primary", slot.primary),
        challenger=slot.challenger,
        fallback=changes.get("fallback", slot.fallback),
    )
    return overlay


def _count_stage_runs(monkeypatch: pytest.MonkeyPatch, *names: str) -> dict[str, int]:
    counts: dict[str, int] = dict.fromkeys(names, 0)
    for name in names:
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


def _semantic(workspace: Path) -> dict[str, Any]:
    return cast("dict[str, Any]", json.loads((workspace / "semantic.json").read_text()))


def _issues(semantic: dict[str, Any]) -> list[dict[str, Any]]:
    store = semantic.get("issues")
    return cast("list[dict[str, Any]]", (store or {}).get("issues", []))


def _statuses(workspace: Path) -> dict[str, str]:
    stages = json.loads((workspace / "workspace.json").read_text())["stages"]
    return {name: record["status"] for name, record in stages.items()}


def test_table_specialist_failure_degrades_and_continues(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A dead Docling dump degrades TABLE to line rows; the rest still runs."""
    fixture = _fixture("table-heavy")
    source = fixture.read_bytes()
    overlay = _overlay("table.structure", primary="docling", fallback="mock")
    monkeypatch.setattr(pipeline, "compile_latex", _fake_compile)
    monkeypatch.setattr(pipeline, "load_registry", lambda: overlay)
    monkeypatch.setenv("DOCLING_DUMP", str(tmp_path / "missing-docling.json"))

    out = tmp_path / "ws"
    pipeline.run_pipeline(fixture, out)

    semantic = _semantic(out)
    tables = [node for node in semantic["nodes"] if node["kind"] == "TABLE"]
    assert tables
    content = tables[0]["content"]
    assert content["columns"] == 1
    assert len(content["cells"]) >= 3
    assert tables[0]["confidence"]["reason"] == "table fallback: line rows"

    provider_issues = [issue for issue in _issues(semantic) if issue["producer"] == "docling"]
    assert len(provider_issues) == 1
    issue = provider_issues[0]
    assert issue["category"] == "TABLE_RECOVERY"
    assert issue["severity"] == "ERROR"
    assert issue["recoverable"] is True
    assert issue["fallback"] == "provider substitution: mock"

    (degradation,) = json.loads((out / "probe.json").read_text())["degradations"]
    assert degradation["provider"] == "docling"
    assert degradation["capabilities"] == ["table.structure", "table.detection"]
    assert degradation["substitutes"] == ["mock"]
    assert degradation["category"] == "TABLE_RECOVERY"

    statuses = _statuses(out)
    assert statuses["evidence"] == "degraded"
    assert [name for name, status in statuses.items() if status != "completed"] == ["evidence"]

    # A degradation is not a completed stage: the next run retries EVIDENCE,
    # and the tail stays skipped because the retry reproduces identical bytes.
    manager = WorkspaceManager(
        out, stage_configs=stage_config_inputs(load_translation_config(), source)
    )
    manager.open_or_create(source)
    record = manager.stage_record(Stage.EVIDENCE)
    assert record is not None
    assert record.status is StageStatus.DEGRADED
    assert not manager.stage_completed(Stage.EVIDENCE)
    assert manager.stage_completed(Stage.LAYOUT)
    assert manager.stage_completed(Stage.SEMANTIC)

    counts = _count_stage_runs(monkeypatch, "_run_evidence_stage", "_run_layout_stage")
    pipeline.run_pipeline(fixture, out)
    assert counts == {"_run_evidence_stage": 1, "_run_layout_stage": 0}


def test_metadata_specialist_failure_keeps_document(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without GROBID the front-matter heuristics still recover the structure."""
    fixture = _fixture("paper-anatomy")
    source = fixture.read_bytes()
    overlay = _overlay("scholarly.metadata", primary="grobid")
    monkeypatch.setattr(pipeline, "compile_latex", _fake_compile)
    monkeypatch.setattr(pipeline, "load_registry", lambda: overlay)
    monkeypatch.setenv("GROBID_DUMP", str(tmp_path / "missing-grobid.json"))

    out = tmp_path / "ws"
    pipeline.run_pipeline(fixture, out)

    semantic = _semantic(out)
    kinds = [node["kind"] for node in semantic["nodes"]]
    assert kinds.count("SECTION") >= 1
    assert kinds.count("PARAGRAPH") >= 1

    provider_issues = [issue for issue in _issues(semantic) if issue["producer"] == "grobid"]
    assert len(provider_issues) == 1
    issue = provider_issues[0]
    assert issue["category"] == "SECTION_STRUCTURE"
    assert issue["severity"] == "ERROR"
    assert issue["fallback"] == "front-matter heuristics"
    assert _statuses(out)["evidence"] == "degraded"
    manager = WorkspaceManager(
        out, stage_configs=stage_config_inputs(load_translation_config(), source)
    )
    manager.open_or_create(source)
    assert not manager.stage_completed(Stage.EVIDENCE)


def test_all_providers_failing_is_a_real_stage_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Zero bundles leaves no evidence authority: EVIDENCE fails loudly."""
    fixture = _fixture("paper-anatomy")
    # Both routed providers are real adapters (layout = mineru, scholarly =
    # grobid) with no dump; binding table.structure to the same layout
    # primary keeps the table route from adding a third provider.
    overlay = dict(load_registry())
    overlay["layout.region"] = Capability(
        name="layout.region", primary="mineru", challenger="docling-sim"
    )
    overlay["table.structure"] = Capability(
        name="table.structure", primary="mineru", fallback="mock"
    )
    overlay["scholarly.metadata"] = Capability(name="scholarly.metadata", primary="grobid")
    monkeypatch.setattr(pipeline, "compile_latex", _fake_compile)
    monkeypatch.setattr(pipeline, "load_registry", lambda: overlay)
    monkeypatch.setenv("MINERU_DUMP", str(tmp_path / "missing-mineru.json"))
    monkeypatch.setenv("GROBID_DUMP", str(tmp_path / "missing-grobid.json"))

    out = tmp_path / "ws"
    with pytest.raises(pipeline.StageExecutionError, match="every routed evidence provider"):
        pipeline.run_pipeline(fixture, out)

    assert not (out / "semantic.json").exists()
    statuses = _statuses(out)
    assert statuses["ingest"] == "completed"
    assert statuses["physical"] == "completed"
    assert "evidence" not in statuses
