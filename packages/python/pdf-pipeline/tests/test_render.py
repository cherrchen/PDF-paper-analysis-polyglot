"""Phase 2.5 + 2.6 tests: LaTeX projection, compile, and render anchors."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from document_model import load_document
from paper_llm import translate_document
from pdf_pipeline.layout import recover_layout_document
from pdf_pipeline.physical import extract_physical_document
from pdf_pipeline.pipeline import region_texts_from, run_pipeline
from pdf_pipeline.render_anchor import recover_render_anchors
from pdf_pipeline.render_composer import compose_render_document
from pdf_pipeline.render_latex import compile_latex, escape_latex, project_to_latex
from pdf_pipeline.semantic import recover_semantic_document

if TYPE_CHECKING:
    from document_model.generated import schema_models as generated

FIXTURE_DIR = Path(__file__).resolve().parents[4] / "tests/fixtures/source/latex/build"


def _fixture(name: str) -> bytes:
    path = FIXTURE_DIR / f"{name}.pdf"
    if not path.exists():
        pytest.skip(f"fixture PDF {name} not built")
    return path.read_bytes()


@pytest.fixture(scope="module")
def smoke_semantic() -> generated.SemanticDocument:
    physical = extract_physical_document(_fixture("smoke"))
    layout = recover_layout_document(physical)
    return recover_semantic_document(layout, region_texts_from(physical, layout))


def test_escape_latex_neutralizes_specials() -> None:
    assert escape_latex("100% & $5 #x") == r"100\% \& \$5 \#x"


def test_escape_latex_removes_pdfium_control_markers() -> None:
    assert escape_latex("moti\x02vates\nwork") == "motivates work"


def test_projection_keeps_tex_out_of_semantic(smoke_semantic: generated.SemanticDocument) -> None:
    for node in smoke_semantic.nodes:
        text = getattr(node.content, "text", None)
        if text:
            # Raw content must not embed TeX commands.
            assert not text.lstrip().startswith("\\")
            assert "\\section" not in text


def test_projection_and_compile_produce_target_pdf(
    tmp_path: Path, smoke_semantic: generated.SemanticDocument
) -> None:
    translation = translate_document(smoke_semantic)
    render = compose_render_document(smoke_semantic, translation)
    tex = project_to_latex(render)
    assert "\\renderanchor{" in tex
    assert "[TRANSLATED] Smoke Fixture" in tex
    pdf = compile_latex(tex, tmp_path / "build")
    assert pdf.exists()
    assert pdf.stat().st_size > 0


def test_render_anchors_recover_all_body_nodes(
    tmp_path: Path, smoke_semantic: generated.SemanticDocument
) -> None:
    translation = translate_document(smoke_semantic)
    render = compose_render_document(smoke_semantic, translation)
    tex = project_to_latex(render)
    pdf = compile_latex(tex, tmp_path / "build")
    anchors = recover_render_anchors(pdf, smoke_semantic)
    body_node_ids = {node.id for node in smoke_semantic.nodes[1:]}
    assert body_node_ids <= {anchor.semanticNodeId for anchor in anchors}
    for anchor in anchors:
        fragment = anchor.fragments[0]
        assert fragment.pageIndex >= 0
        assert fragment.geometry.kind == "rect"
        assert fragment.geometry.width > 0
        assert fragment.geometry.height > 0


def test_end_to_end_pipeline_runs_and_validates(tmp_path: Path) -> None:
    paths = run_pipeline(FIXTURE_DIR / "smoke.pdf", tmp_path / "out")
    for name in (
        "physical.json",
        "layout.json",
        "semantic.json",
        "translation.json",
        "render.json",
        "mapping.json",
    ):
        path = tmp_path / "out" / name
        assert path.exists(), name
        data = json.loads(path.read_text())
        load_document(_kind(name), data)
    assert paths["target.pdf"].exists()
    viewer_mapping = json.loads(
        (tmp_path / "out/viewer/data/mapping.json").read_text(encoding="utf-8")
    )
    assert viewer_mapping["viewerDataVersion"] == 1
    assert viewer_mapping["sourceRegions"]


def test_figure_and_caption_share_one_float() -> None:
    physical = extract_physical_document(_fixture("figure-caption"))
    layout = recover_layout_document(physical)
    semantic = recover_semantic_document(layout, region_texts_from(physical, layout))
    translation = translate_document(semantic)
    render = compose_render_document(semantic, translation)
    tex = project_to_latex(render)

    assert sum(node.kind == "FIGURE" for node in semantic.nodes) == 1
    assert sum(node.kind == "FIGURE_CAPTION" for node in semantic.nodes) == 1
    assert tex.count("\\begin{figure}") == 1
    assert "\\caption{" in tex


@pytest.mark.integration
@pytest.mark.rendering
@pytest.mark.parametrize(
    "fixture",
    [
        "bibliography",
        "cross-page-paragraph",
        "equation-heavy",
        "figure-caption",
        "footnote-multicolumn",
        "mixed-bands",
        "smoke",
        "spanning-figure",
        "table-heavy",
        "tikz-vector",
        "two-column",
    ],
)
def test_tier1_pipeline_compiles_every_fixture(tmp_path: Path, fixture: str) -> None:
    paths = run_pipeline(FIXTURE_DIR / f"{fixture}.pdf", tmp_path / fixture)
    assert paths["target.pdf"].exists()


def _kind(name: str) -> str:
    return {
        "physical.json": "physical-document",
        "layout.json": "layout-document",
        "semantic.json": "semantic-document",
        "translation.json": "translation-layer",
        "render.json": "render-document",
        "mapping.json": "mapping",
    }[name]
