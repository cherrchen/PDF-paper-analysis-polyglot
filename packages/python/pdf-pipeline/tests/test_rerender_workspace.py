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
def workspace(tmp_path: Path) -> Path:
    """A workspace built by run_pipeline on the smoke fixture (real compile)."""
    fixture = Path(__file__).resolve().parents[4] / "tests/fixtures/source/latex/build/smoke.pdf"
    if not fixture.exists():
        pytest.skip("smoke fixture PDF not built; run `just latex-smoke`")
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
