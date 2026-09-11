"""M5 review-repair tests for LaTeX projection, CJK, overflow, and anchors."""

# pyright: reportUnknownMemberType=false, reportAttributeAccessIssue=false

from __future__ import annotations

import struct
import zlib
from pathlib import Path
from typing import TYPE_CHECKING

import pypdfium2 as pdfium
import pytest
from document_model.generated import schema_models as generated
from paper_llm.config import ProviderConfig, TranslationConfig
from paper_llm.translation import DummyTranslationProvider
from pdf_pipeline.pipeline import run_pipeline
from pdf_pipeline.render_anchor import recover_render_anchors
from pdf_pipeline.render_composer import DEFAULT_POLICY, DEFAULT_PROFILE, compose_render_document
from pdf_pipeline.render_latex import compile_latex, project_to_latex

if TYPE_CHECKING:
    from collections.abc import Sequence

DOC_ID = "00000000-0000-0000-0000-000000000202"
SEM_ID = "00000000-0000-0000-0000-000000000101"
TR_ID = "00000000-0000-0000-0000-000000000201"
ROOT_ID = "00000000-0000-0000-0000-000000000102"
NODE_A = "00000000-0000-0000-0000-000000000111"
NODE_B = "00000000-0000-0000-0000-000000000112"
BLOCK_ID = "00000000-0000-0000-0000-000000000203"
FIXTURE_DIR = Path(__file__).resolve().parents[4] / "tests/fixtures/source/latex/build"


def _policy(**overrides: object) -> generated.RenderPolicy:
    return DEFAULT_POLICY.model_copy(update=overrides)


def _render(
    blocks: Sequence[generated.RenderBlock],
    *,
    policy: generated.RenderPolicy | None = None,
) -> generated.RenderDocument:
    return generated.RenderDocument(
        schemaVersion="0.2.0",
        id=DOC_ID,
        semanticDocumentId=SEM_ID,
        translationLayerId=TR_ID,
        profile=DEFAULT_PROFILE,
        policy=policy or DEFAULT_POLICY,
        blocks=list(blocks),
        provenanceIds=[],
    )


def _semantic(*nodes: generated.SemanticNode) -> generated.SemanticDocument:
    root = generated.SemanticNode.model_validate(
        {
            "id": ROOT_ID,
            "kind": "DOCUMENT",
            "children": [node.id for node in nodes],
            "content": {"text": "", "marks": []},
            "attributes": {},
            "confidence": {"score": 1.0},
            "provenanceIds": [],
        }
    )
    return generated.SemanticDocument(
        schemaVersion="0.1.0",
        id=SEM_ID,
        rootId=ROOT_ID,
        nodes=[root, *nodes],
        relations=[],
        provenanceIds=[],
    )


def _paragraph_node(node_id: str, text: str) -> generated.SemanticNode:
    return generated.SemanticNode.model_validate(
        {
            "id": node_id,
            "kind": "PARAGRAPH",
            "parentId": ROOT_ID,
            "children": [],
            "content": {"text": text, "marks": []},
            "attributes": {},
            "confidence": {"score": 1.0},
            "provenanceIds": [],
        }
    )


def _write_tiny_png(path: Path) -> None:
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 0, 0, 0, 0)
    idat = zlib.compress(b"\x00\x00", 9)

    def chunk(tag: bytes, data: bytes) -> bytes:
        checksum = zlib.crc32(tag)
        checksum = zlib.crc32(data, checksum) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", checksum)

    path.write_bytes(
        b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")
    )


def _pdf_text(pdf_path: Path) -> str:
    document = pdfium.PdfDocument(str(pdf_path))
    try:
        chunks: list[str] = []
        for page in document:
            textpage = page.get_textpage()
            chunks.append(textpage.get_text_bounded())
        return "\n".join(chunks)
    finally:
        document.close()


def _log_text(out_dir: Path, job_name: str = "target") -> str:
    return (out_dir / f"{job_name}.log").read_text(encoding="utf-8", errors="replace")


@pytest.mark.unit
def test_figure_anchors_live_inside_float() -> None:
    block = generated.RenderFigureBlock(
        renderKind="FIGURE",
        id=BLOCK_ID,
        semanticNodeIds=[NODE_A, NODE_B],
        figure=generated.FigureContent(resources=generated.FigureResource(embeddedImageIds=[])),
        caption=generated.RichText(text="A figure", marks=[]),
    )
    tex = project_to_latex(_render([block]))
    figure_start = tex.index("\\begin{figure}")
    figure_end = tex.index("\\end{figure}")
    anchor = tex.index(f"\\renderanchor{{{NODE_A}}}")
    anchor_end = tex.index(f"\\renderanchorend{{{NODE_A}}}")
    assert figure_start < anchor < anchor_end < figure_end


@pytest.mark.unit
def test_equation_preserves_source_number() -> None:
    block = generated.RenderEquationBlock(
        renderKind="EQUATION",
        id=BLOCK_ID,
        semanticNodeIds=[NODE_A],
        equation=generated.EquationContent(latex="E = mc^2", number="7"),
    )
    tex = project_to_latex(_render([block]))
    assert r"\tag{7}" in tex
    assert r"\fitmath{" in tex


@pytest.mark.unit
def test_non_float_table_caption_uses_captionof_above_and_below() -> None:
    table = generated.TableContent(
        rows=1,
        columns=1,
        cells=[
            generated.TableCell(
                row=0,
                column=0,
                rowSpan=1,
                colSpan=1,
                content=generated.RichText(text="cell", marks=[]),
            )
        ],
    )
    block = generated.RenderTableBlock(
        renderKind="TABLE",
        id=BLOCK_ID,
        semanticNodeIds=[NODE_A, NODE_B],
        table=table,
        caption=generated.RichText(text="A table", marks=[]),
        columnAlignments=["LEFT"],
    )
    above = project_to_latex(
        _render([block], policy=_policy(floatTables=False, captionPosition="ABOVE"))
    )
    below = project_to_latex(
        _render([block], policy=_policy(floatTables=False, captionPosition="BELOW"))
    )
    assert r"\captionof{table}{A table}" in above
    assert r"\captionof{table}{A table}" in below
    assert r"\begin{center}" in above
    assert above.index(r"\captionof{table}") < above.index(r"\begin{tabular}")
    assert below.index(r"\begin{tabular}") < below.index(r"\captionof{table}")


@pytest.mark.unit
def test_table_projection_keeps_spans_and_empty_columns() -> None:
    table = generated.TableContent(
        rows=2,
        columns=3,
        cells=[
            generated.TableCell(
                row=0,
                column=0,
                rowSpan=2,
                colSpan=2,
                content=generated.RichText(text="span", marks=[]),
            ),
            generated.TableCell(
                row=0,
                column=2,
                rowSpan=1,
                colSpan=1,
                content=generated.RichText(text="c", marks=[]),
            ),
        ],
    )
    block = generated.RenderTableBlock(
        renderKind="TABLE",
        id=BLOCK_ID,
        semanticNodeIds=[NODE_A],
        table=table,
        columnAlignments=["LEFT", "CENTER", "RIGHT"],
    )
    tex = project_to_latex(_render([block]))
    assert r"\multirow{2}{*}{span}" in tex
    assert r"\multicolumn{2}{l}{\multirow{2}{*}{span}}" in tex
    assert r"\begin{tabular}{lcr}" in tex
    assert r"\fitbox{%" in tex


@pytest.mark.unit
def test_compose_does_not_guess_figure_resources_by_index() -> None:
    figure = generated.SemanticNode.model_validate(
        {
            "id": NODE_A,
            "kind": "FIGURE",
            "parentId": ROOT_ID,
            "children": [],
            "content": {"resources": {"embeddedImageIds": []}},
            "attributes": {},
            "confidence": {"score": 1.0},
            "provenanceIds": [],
        }
    )
    translation = generated.TranslationLayer(
        schemaVersion="0.2.0",
        id=TR_ID,
        semanticDocumentId=SEM_ID,
        targetLocale="zh-CN",
        entries=[],
        provenanceIds=[],
    )
    resources = generated.ResourceStore(
        resources=[
            generated.ResourceRecord(
                id="00000000-0000-0000-0000-000000000001",
                kind="EMBEDDED_IMAGE",
                mediaType="image/png",
                origin="EXTRACTED",
            )
        ]
    )
    render = compose_render_document(
        _semantic(figure),
        translation,
        resources=resources,
    )
    figure_blocks = [block for block in render.blocks if block.renderKind == "FIGURE"]
    assert figure_blocks
    assert not figure_blocks[0].resourceIds


@pytest.mark.rendering
def test_chinese_paragraph_renders_without_missing_characters(tmp_path: Path) -> None:
    block = generated.RenderParagraphBlock(
        renderKind="PARAGRAPH",
        id=BLOCK_ID,
        semanticNodeIds=[NODE_A],
        content=generated.RichText(text="参见中文译文。", marks=[]),
    )
    tex = project_to_latex(_render([block]))
    pdf = compile_latex(tex, tmp_path / "build")
    log = _log_text(tmp_path / "build")
    assert "Missing character" not in log
    assert "参见" in _pdf_text(pdf)


@pytest.mark.rendering
def test_unicode_equation_compiles_with_command_boundaries(tmp_path: Path) -> None:
    block = generated.RenderEquationBlock(
        renderKind="EQUATION",
        id=BLOCK_ID,
        semanticNodeIds=[NODE_A],
        equation=generated.EquationContent(unicodeText="\u03b1x = \u03b2y"),
    )
    tex = project_to_latex(_render([block]))
    assert r"\alpha{}x = \beta{}y" in tex
    compile_latex(tex, tmp_path / "build")
    assert "Undefined control sequence" not in _log_text(tmp_path / "build")


@pytest.mark.rendering
@pytest.mark.parametrize("position", ["ABOVE", "BELOW"])
def test_non_float_table_with_caption_compiles(tmp_path: Path, position: str) -> None:
    table = generated.TableContent(
        rows=1,
        columns=1,
        cells=[
            generated.TableCell(
                row=0,
                column=0,
                rowSpan=1,
                colSpan=1,
                content=generated.RichText(text="cell", marks=[]),
            )
        ],
    )
    block = generated.RenderTableBlock(
        renderKind="TABLE",
        id=BLOCK_ID,
        semanticNodeIds=[NODE_A, NODE_B],
        table=table,
        caption=generated.RichText(text="A table", marks=[]),
        columnAlignments=["LEFT"],
    )
    tex = project_to_latex(
        _render([block], policy=_policy(floatTables=False, captionPosition=position))
    )
    compile_latex(tex, tmp_path / "build")
    assert "caption outside float" not in _log_text(tmp_path / "build").lower()


@pytest.mark.rendering
def test_relative_resource_dir_image_path_compiles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    resource_dir = Path("out/resources")
    resource_dir.mkdir(parents=True)
    resource_id = "00000000-0000-0000-0000-000000000099"
    _write_tiny_png(resource_dir / f"{resource_id}.png")
    block = generated.RenderFigureBlock(
        renderKind="FIGURE",
        id=BLOCK_ID,
        semanticNodeIds=[NODE_A],
        figure=generated.FigureContent(
            resources=generated.FigureResource(embeddedImageIds=[resource_id])
        ),
        resourceIds=[resource_id],
    )
    tex = project_to_latex(_render([block]), resource_dir=resource_dir)
    assert (resource_dir / f"{resource_id}.png").resolve().as_posix() in tex
    compile_latex(tex, Path("out/build"))


@pytest.mark.rendering
def test_cross_page_paragraph_covers_intermediate_pages(tmp_path: Path) -> None:
    text = " ".join(["This sentence continues across many pages of the target PDF."] * 400)
    block = generated.RenderParagraphBlock(
        renderKind="PARAGRAPH",
        id=BLOCK_ID,
        semanticNodeIds=[NODE_A],
        content=generated.RichText(text=text, marks=[]),
    )
    tex = project_to_latex(_render([block]))
    pdf = compile_latex(tex, tmp_path / "build")
    document = pdfium.PdfDocument(str(pdf))
    try:
        page_count = len(document)
    finally:
        document.close()
    assert page_count >= 3
    anchors = recover_render_anchors(pdf, _semantic(_paragraph_node(NODE_A, text)))
    assert len(anchors) == 1
    pages = [fragment.pageIndex for fragment in anchors[0].fragments]
    assert pages == list(range(pages[0], pages[-1] + 1))
    assert len(pages) >= 3
    for fragment in anchors[0].fragments:
        assert fragment.geometry.height > 12.0
        assert fragment.geometry.width > 12.0


@pytest.mark.integration
def test_run_pipeline_uses_passed_provider_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    smoke = FIXTURE_DIR / "smoke.pdf"
    if not smoke.exists():
        pytest.skip("smoke fixture not built")
    seen: dict[str, ProviderConfig | None] = {}

    def fake_create(
        *,
        provider_model: str = "dummy",
        provider_config: ProviderConfig | None = None,
    ) -> DummyTranslationProvider:
        del provider_model
        seen["config"] = provider_config
        return DummyTranslationProvider()

    monkeypatch.setattr("pdf_pipeline.pipeline.create_provider", fake_create)
    monkeypatch.setenv("PAPER_LLM_ENDPOINT", "http://from-env.example")
    monkeypatch.setenv("PAPER_LLM_MODEL", "env-model")
    passed = ProviderConfig(
        endpoint="http://from-config.example", api_key=None, model="config-model"
    )
    run_pipeline(
        smoke,
        tmp_path / "out",
        translation_config=TranslationConfig(
            target_locale="zh-CN",
            source_locale=None,
            terminology_file=None,
            cache_dir=None,
            provider=passed,
        ),
    )
    assert seen["config"] is passed
    assert passed.endpoint == "http://from-config.example"
    assert passed.model == "config-model"


@pytest.mark.rendering
def test_malformed_equations_compile_via_text_fallback(tmp_path: Path) -> None:
    for text in ("x__1", "cost $5"):
        block = generated.RenderEquationBlock(
            renderKind="EQUATION",
            id=BLOCK_ID,
            semanticNodeIds=[NODE_A],
            equation=generated.EquationContent(unicodeText=text),
        )
        tex = project_to_latex(_render([block]))
        compile_latex(tex, tmp_path / text.replace(" ", "_").replace("$", "dollar"))
        log = _log_text(tmp_path / text.replace(" ", "_").replace("$", "dollar"))
        assert "Missing { inserted" not in log
        assert "Extra }, or forgotten $" not in log


@pytest.mark.rendering
def test_sqrt_equation_keeps_operand_inside_radical(tmp_path: Path) -> None:
    block = generated.RenderEquationBlock(
        renderKind="EQUATION",
        id=BLOCK_ID,
        semanticNodeIds=[NODE_A],
        equation=generated.EquationContent(unicodeText="√x"),
    )
    tex = project_to_latex(_render([block]))
    assert r"\sqrt{x}" in tex
    assert r"\sqrt{}x" not in tex
    compile_latex(tex, tmp_path / "build")


@pytest.mark.unit
def test_figure_projects_every_bound_resource(tmp_path: Path) -> None:
    resource_dir = tmp_path / "resources"
    resource_dir.mkdir()
    first = "00000000-0000-0000-0000-000000000091"
    second = "00000000-0000-0000-0000-000000000092"
    _write_tiny_png(resource_dir / f"{first}.png")
    _write_tiny_png(resource_dir / f"{second}.png")
    block = generated.RenderFigureBlock(
        renderKind="FIGURE",
        id=BLOCK_ID,
        semanticNodeIds=[NODE_A, NODE_B],
        figure=generated.FigureContent(
            resources=generated.FigureResource(embeddedImageIds=[first, second])
        ),
        caption=generated.RichText(text="Two panels", marks=[]),
        resourceIds=[first, second],
    )
    tex = project_to_latex(_render([block]), resource_dir=resource_dir)
    assert tex.count("\\includegraphics") == 2
    assert first in tex
    assert second in tex
    above = project_to_latex(
        _render([block], policy=_policy(captionPosition="ABOVE")),
        resource_dir=resource_dir,
    )
    caption_at = above.index(r"\caption{Two panels}")
    graphic_at = above.index(r"\includegraphics")
    assert caption_at < graphic_at


@pytest.mark.unit
def test_render_policy_wide_figure_and_table_overflow() -> None:
    resource_id = "00000000-0000-0000-0000-000000000093"
    figure = generated.RenderFigureBlock(
        renderKind="FIGURE",
        id=BLOCK_ID,
        semanticNodeIds=[NODE_A],
        figure=generated.FigureContent(
            resources=generated.FigureResource(embeddedImageIds=[resource_id])
        ),
        resourceIds=[resource_id],
    )
    wide = project_to_latex(_render([figure], policy=_policy(wideFigureHandling="WIDE_FLOAT")))
    inline = project_to_latex(_render([figure], policy=_policy(wideFigureHandling="INLINE")))
    assert r"\begin{figure*}" in wide
    assert r"\end{figure*}" in wide
    assert r"\begin{figure}" not in inline
    assert r"\begin{center}" in inline

    table = generated.TableContent(
        rows=1,
        columns=1,
        cells=[
            generated.TableCell(
                row=0,
                column=0,
                rowSpan=1,
                colSpan=1,
                content=generated.RichText(text="cell", marks=[]),
            )
        ],
    )
    block = generated.RenderTableBlock(
        renderKind="TABLE",
        id=BLOCK_ID,
        semanticNodeIds=[NODE_A],
        table=table,
        columnAlignments=["LEFT"],
    )
    wrap = project_to_latex(_render([block], policy=_policy(tableOverflowHandling="WRAP")))
    fail = project_to_latex(_render([block], policy=_policy(tableOverflowHandling="FAIL")))
    wide_table = project_to_latex(
        _render([block], policy=_policy(tableOverflowHandling="WIDE_FLOAT"))
    )
    assert r"p{\dimexpr" in wrap
    assert r"\errmessage{table overflow with FAIL policy}" in fail
    assert r"\begin{table*}" in wide_table


@pytest.mark.unit
def test_compose_records_multi_image_layout_issue() -> None:
    first = "00000000-0000-0000-0000-000000000091"
    second = "00000000-0000-0000-0000-000000000092"
    figure = generated.SemanticNode.model_validate(
        {
            "id": NODE_A,
            "kind": "FIGURE",
            "parentId": ROOT_ID,
            "children": [],
            "content": {"resources": {"embeddedImageIds": [first, second]}},
            "attributes": {},
            "confidence": {"score": 1.0},
            "provenanceIds": [],
        }
    )
    translation = generated.TranslationLayer(
        schemaVersion="0.2.0",
        id=TR_ID,
        semanticDocumentId=SEM_ID,
        targetLocale="zh-CN",
        entries=[],
        provenanceIds=[],
    )
    resources = generated.ResourceStore(
        resources=[
            generated.ResourceRecord(
                id=first, kind="EMBEDDED_IMAGE", mediaType="image/png", origin="EXTRACTED"
            ),
            generated.ResourceRecord(
                id=second, kind="EMBEDDED_IMAGE", mediaType="image/png", origin="EXTRACTED"
            ),
        ]
    )
    render = compose_render_document(
        _semantic(figure),
        translation,
        resources=resources,
        policy=_policy(captionPosition="SOURCE"),
    )
    figure_blocks = [block for block in render.blocks if block.renderKind == "FIGURE"]
    assert figure_blocks[0].resourceIds == [first, second]
    assert render.issues is not None
    messages = [issue.message for issue in render.issues.issues]
    assert any("multiple bound images" in message for message in messages)


@pytest.mark.rendering
def test_multi_resource_figure_compiles(tmp_path: Path) -> None:
    resource_dir = tmp_path / "resources"
    resource_dir.mkdir()
    first = "00000000-0000-0000-0000-000000000091"
    second = "00000000-0000-0000-0000-000000000092"
    _write_tiny_png(resource_dir / f"{first}.png")
    _write_tiny_png(resource_dir / f"{second}.png")
    block = generated.RenderFigureBlock(
        renderKind="FIGURE",
        id=BLOCK_ID,
        semanticNodeIds=[NODE_A],
        figure=generated.FigureContent(
            resources=generated.FigureResource(embeddedImageIds=[first, second])
        ),
        resourceIds=[first, second],
    )
    tex = project_to_latex(_render([block]), resource_dir=resource_dir)
    compile_latex(tex, tmp_path / "build")
