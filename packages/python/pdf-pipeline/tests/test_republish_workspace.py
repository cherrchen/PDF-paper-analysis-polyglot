# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false
"""republish_workspace_viewer: publish committed artifacts, run no stage.

LaTeX compilation is faked (empty PDFium pages) exactly as in
`test_rerender_workspace.py`, so the republish chain is exercised without the
toolchain. `recover_render_anchors` on a destination-less PDF returns [].
"""

from __future__ import annotations

import json
from pathlib import Path

import pypdfium2 as pdfium
import pytest
from pdf_pipeline import pipeline
from pdf_pipeline.pipeline import republish_workspace_viewer
from pdf_pipeline.workspace import MANIFEST_NAME, WorkspaceError


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
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A workspace committed by run_pipeline, already published to ``viewer-a``."""
    fixture = Path(__file__).resolve().parents[4] / "tests/fixtures/source/latex/build/smoke.pdf"
    if not fixture.exists():
        pytest.skip("smoke fixture PDF not built; run `just latex-smoke`")
    monkeypatch.setattr(pipeline, "compile_latex", _fake_compile)
    out = tmp_path / "ws"
    pipeline.run_pipeline(fixture, out, viewer_data_dir=tmp_path / "viewer-a")
    return out


def _revision_of(data_dir: Path) -> str:
    manifest = json.loads((data_dir / "manifest.json").read_text(encoding="utf-8"))
    return str(manifest["revision"])


def _tree(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_republish_reproduces_the_index_publication(workspace: Path) -> None:
    published = workspace.parent / "viewer-a"
    index_revision = _revision_of(published)
    target = workspace.parent / "viewer-b"
    workspace_before = _tree(workspace)

    revision = republish_workspace_viewer(workspace, viewer_data_dir=target)

    assert revision == _revision_of(target)
    assert revision != index_revision
    assert (target / "mapping.json").read_bytes() == (published / "mapping.json").read_bytes()
    assert (target / "viewer-meta.json").read_bytes() == (
        published / "viewer-meta.json"
    ).read_bytes()
    assert (target / "source.pdf").read_bytes() == (workspace / "source.pdf").read_bytes()
    assert (target / "target.pdf").read_bytes() == (workspace / "target.pdf").read_bytes()
    manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["workspace"] == str(workspace.resolve())
    viewer_mapping = json.loads((target / "mapping.json").read_text(encoding="utf-8"))
    assert viewer_mapping["viewerDataVersion"] == 2
    assert viewer_mapping["translation"]["entries"]
    # The fake compile has no named destinations: anchors degrade to empty
    # instead of carrying stale geometry.
    assert viewer_mapping["renderAnchors"] == []
    # The publication receipt belongs to the INDEX writer; a republish must not
    # claim it, or the next run_pipeline would skip a publication it never did.
    assert _tree(workspace) == workspace_before


def test_republish_publishes_a_fresh_revision_each_time(workspace: Path) -> None:
    viewer = workspace.parent / "viewer-a"
    first = _revision_of(viewer)

    second = republish_workspace_viewer(workspace, viewer_data_dir=viewer)
    third = republish_workspace_viewer(workspace, viewer_data_dir=viewer)

    assert len({first, second, third}) == 3
    assert _revision_of(viewer) == third
    assert sorted(path.name for path in (viewer / "revisions").iterdir()) == sorted([third, second])


def test_republish_refuses_an_uncommitted_workspace(workspace: Path) -> None:
    (workspace / "target.pdf").unlink()

    with pytest.raises(WorkspaceError, match="not committed"):
        republish_workspace_viewer(workspace, viewer_data_dir=workspace.parent / "viewer-b")


def test_republish_refuses_a_workspace_without_a_manifest(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    root.mkdir()

    with pytest.raises(WorkspaceError, match="missing workspace manifest"):
        republish_workspace_viewer(root, viewer_data_dir=tmp_path / "viewer")


def test_republish_refuses_a_manifest_bound_to_another_source(workspace: Path) -> None:
    (workspace / "source.pdf").write_bytes(b"%PDF-1.4\nreplace the committed source\n")

    with pytest.raises(WorkspaceError, match="different source PDF"):
        republish_workspace_viewer(workspace, viewer_data_dir=workspace.parent / "viewer-b")


def test_republish_refuses_an_unsupported_manifest_version(workspace: Path, tmp_path: Path) -> None:
    manifest = json.loads((workspace / MANIFEST_NAME).read_text(encoding="utf-8"))
    manifest["workspaceVersion"] = "9.9.9"
    (workspace / MANIFEST_NAME).write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(WorkspaceError, match=r"9\.9\.9"):
        republish_workspace_viewer(workspace, viewer_data_dir=tmp_path / "viewer-b")

    assert not (tmp_path / "viewer-b" / "manifest.json").exists()
