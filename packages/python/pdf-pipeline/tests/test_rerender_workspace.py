# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false
"""M6 rerender_workspace: local re-translation without re-parsing the source.

LaTeX compilation is faked (empty PDFium pages) so the unit test exercises the
workspace load → retranslate → compose → mapping-rebuild → viewer-rewrite
chain without the toolchain; `recover_render_anchors` on a destination-less
PDF returns [], which keeps the mapping valid.
"""

from __future__ import annotations

import json
from pathlib import Path

import pypdfium2 as pdfium
import pytest
from document_model import load_document
from document_model.generated import schema_models as generated
from paper_llm.config import TranslationConfig
from paper_llm.translation import TranslationProviderNotConfiguredError
from paper_llm.types import TranslationRequest, TranslationResult
from pdf_pipeline import pipeline
from pdf_pipeline.pipeline import rerender_workspace


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


def _load_translation(workspace: Path) -> generated.TranslationLayer:
    layer = load_document(
        "translation-layer", json.loads((workspace / "translation.json").read_text())
    )
    assert isinstance(layer, generated.TranslationLayer)
    return layer


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A workspace built by run_pipeline on the smoke fixture (fake compile)."""
    fixture = Path(__file__).resolve().parents[4] / "tests/fixtures/source/latex/build/smoke.pdf"
    if not fixture.exists():
        pytest.skip("smoke fixture PDF not built; run `just latex-smoke`")
    monkeypatch.setattr(pipeline, "compile_latex", _fake_compile)
    out = tmp_path / "ws"
    pipeline.run_pipeline(fixture, out)
    return out


def test_rerender_rewrites_translation_and_viewer_data(
    workspace: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    translation = _load_translation(workspace)
    entry_ids = sorted(entry.semanticNodeId for entry in translation.entries)
    assert entry_ids

    monkeypatch.setattr(pipeline, "compile_latex", _fake_compile)
    viewer_dir = tmp_path / "viewer"
    changed = rerender_workspace(workspace, viewer_data_dir=viewer_dir, node_ids={entry_ids[0]})
    assert changed == [entry_ids[0]]

    after = _load_translation(workspace)
    # Dummy provider is deterministic: same ids, same provider model.
    assert sorted(e.semanticNodeId for e in after.entries) == entry_ids
    assert after.providerModel == translation.providerModel == "dummy"
    assert after.entries == translation.entries

    viewer_mapping = json.loads((viewer_dir / "mapping.json").read_text())
    assert viewer_mapping["viewerDataVersion"] == 2
    assert viewer_mapping["translation"]["entries"]
    # Fake compile has no named destinations -> no render anchors; navigation
    # data degrades to empty, not stale geometry.
    assert viewer_mapping["renderAnchors"] == []
    assert (workspace / "source.pdf").exists()
    assert (viewer_dir / "source.pdf").exists()
    assert (viewer_dir / "target.pdf").exists()
    meta = json.loads((viewer_dir / "viewer-meta.json").read_text())
    assert len(meta["sourcePages"]) == meta["sourcePageCount"]
    assert len(meta["targetPages"]) == meta["targetPageCount"]
    manifest = json.loads((viewer_dir / "manifest.json").read_text())
    assert manifest["revision"]
    rev_dir = viewer_dir / "revisions" / manifest["revision"]
    assert (rev_dir / "mapping.json").is_file()
    assert (rev_dir / "target.pdf").is_file()


def test_rerender_rejects_unknown_nodes(workspace: Path, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="not re-translatable nodes"):
        rerender_workspace(
            workspace,
            viewer_data_dir=tmp_path / "viewer",
            node_ids={"00000000-0000-0000-0000-000000000000"},
        )


def test_rerender_missing_workspace_raises_file_not_found(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError) as error:
        rerender_workspace(
            tmp_path / "nope",
            viewer_data_dir=tmp_path / "viewer",
            node_ids={"anything"},
        )
    assert "nope" in str(error.value)


def test_rerender_never_reparses_source_pdf(
    workspace: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("rerender must not re-run physical extraction")

    monkeypatch.setattr(pipeline, "extract_physical_document", boom)
    monkeypatch.setattr(pipeline, "compile_latex", _fake_compile)
    node_id = _load_translation(workspace).entries[0].semanticNodeId
    rerender_workspace(workspace, viewer_data_dir=tmp_path / "viewer", node_ids={node_id})


class _LabeledProvider:
    def __init__(self, label: str) -> None:
        self.label = label
        self.calls = 0

    def translate_request(self, request: TranslationRequest) -> TranslationResult:
        self.calls += 1
        return TranslationResult(text=f"{self.label}:{request.text}", marks=[])


def test_rerender_records_current_provider_identity(
    workspace: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    translation = _load_translation(workspace)
    node_id = translation.entries[0].semanticNodeId
    other_id = translation.entries[1].semanticNodeId
    labeled = _LabeledProvider("model-b")

    def fake_build(_config: TranslationConfig) -> tuple[object, str, str, None]:
        return labeled, "openai-compat:model-b", "http://llm.example", None

    monkeypatch.setattr(pipeline, "_build_translation_provider", fake_build)
    monkeypatch.setattr(pipeline, "compile_latex", _fake_compile)
    rerender_workspace(workspace, viewer_data_dir=tmp_path / "viewer", node_ids={node_id})
    after = _load_translation(workspace)
    by_id = {entry.semanticNodeId: entry for entry in after.entries}
    assert by_id[node_id].providerModel == "openai-compat:model-b"
    assert str(by_id[node_id].content.text).startswith("model-b:")
    assert by_id[other_id].providerModel == translation.entries[1].providerModel
    assert after.providerModel == "openai-compat:model-b"
    assert labeled.calls >= 1


def test_rerender_real_workspace_without_provider_errors(workspace: Path, tmp_path: Path) -> None:
    from document_model import dump_document

    translation = _load_translation(workspace)
    dump_document(
        translation.model_copy(update={"providerModel": "openai-compat:gpt-4o"}),
        path=workspace / "translation.json",
    )
    config = TranslationConfig(
        target_locale="zh-CN",
        source_locale=None,
        terminology_file=None,
        cache_dir=None,
        provider=None,
    )
    with pytest.raises(TranslationProviderNotConfiguredError):
        rerender_workspace(
            workspace,
            viewer_data_dir=tmp_path / "viewer",
            node_ids={translation.entries[0].semanticNodeId},
            translation_config=config,
        )
    assert _load_translation(workspace).providerModel == "openai-compat:gpt-4o"


def test_rerender_compile_failure_keeps_previous_revision(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    viewer = workspace / "viewer" / "data"
    before_translation = (workspace / "translation.json").read_text(encoding="utf-8")
    before_manifest = (viewer / "manifest.json").read_text(encoding="utf-8")
    node_id = _load_translation(workspace).entries[0].semanticNodeId

    def boom(*_args: object, **_kwargs: object) -> Path:
        raise RuntimeError("compile failed")

    monkeypatch.setattr(pipeline, "compile_latex", boom)
    with pytest.raises(RuntimeError, match="compile failed"):
        rerender_workspace(workspace, viewer_data_dir=viewer, node_ids={node_id})
    assert (workspace / "translation.json").read_text(encoding="utf-8") == before_translation
    assert (viewer / "manifest.json").read_text(encoding="utf-8") == before_manifest


def test_rerender_validate_failure_keeps_previous_revision(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    viewer = workspace / "viewer" / "data"
    before_translation = (workspace / "translation.json").read_text(encoding="utf-8")
    before_manifest = (viewer / "manifest.json").read_text(encoding="utf-8")
    node_id = _load_translation(workspace).entries[0].semanticNodeId
    monkeypatch.setattr(pipeline, "compile_latex", _fake_compile)
    monkeypatch.setattr(pipeline, "validate_bundle_references", lambda *_a, **_k: ["injected"])
    with pytest.raises(RuntimeError, match="bundle reference issues"):
        rerender_workspace(workspace, viewer_data_dir=viewer, node_ids={node_id})
    assert (workspace / "translation.json").read_text(encoding="utf-8") == before_translation
    assert (viewer / "manifest.json").read_text(encoding="utf-8") == before_manifest


def test_rerender_publish_failure_keeps_previous_revision(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    viewer = workspace / "viewer" / "data"
    before_translation = (workspace / "translation.json").read_text(encoding="utf-8")
    before_manifest = (viewer / "manifest.json").read_text(encoding="utf-8")
    node_id = _load_translation(workspace).entries[0].semanticNodeId
    monkeypatch.setattr(pipeline, "compile_latex", _fake_compile)

    def boom(*_args: object, **_kwargs: object) -> str:
        raise RuntimeError("publish failed")

    monkeypatch.setattr(pipeline, "_publish_viewer_revision", boom)
    with pytest.raises(RuntimeError, match="publish failed"):
        rerender_workspace(workspace, viewer_data_dir=viewer, node_ids={node_id})
    assert (workspace / "translation.json").read_text(encoding="utf-8") == before_translation
    assert (viewer / "manifest.json").read_text(encoding="utf-8") == before_manifest


def test_rerender_keeps_previous_revision_readable(
    workspace: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    viewer = tmp_path / "viewer"
    monkeypatch.setattr(pipeline, "compile_latex", _fake_compile)
    node_id = _load_translation(workspace).entries[0].semanticNodeId
    rerender_workspace(workspace, viewer_data_dir=viewer, node_ids={node_id})
    first = json.loads((viewer / "manifest.json").read_text(encoding="utf-8"))
    first_mapping = (viewer / "revisions" / first["revision"] / "mapping.json").read_text(
        encoding="utf-8"
    )

    def three_page_compile(tex: Path, build_dir: Path) -> Path:
        del tex
        build_dir.mkdir(parents=True, exist_ok=True)
        out = build_dir / "target.pdf"
        doc = pdfium.PdfDocument.new()
        for _ in range(3):
            doc.new_page(612, 792)
        doc.save(out)
        doc.close()
        return out

    monkeypatch.setattr(pipeline, "compile_latex", three_page_compile)
    rerender_workspace(workspace, viewer_data_dir=viewer, node_ids={node_id})
    second = json.loads((viewer / "manifest.json").read_text(encoding="utf-8"))
    assert second["revision"] != first["revision"]
    assert (viewer / "revisions" / first["revision"] / "mapping.json").read_text(
        encoding="utf-8"
    ) == first_mapping
    meta = json.loads((viewer / "viewer-meta.json").read_text(encoding="utf-8"))
    assert meta["targetPageCount"] == 3
    concurrent = json.loads(
        (viewer / "revisions" / first["revision"] / "viewer-meta.json").read_text(encoding="utf-8")
    )
    assert concurrent["targetPageCount"] == 2
