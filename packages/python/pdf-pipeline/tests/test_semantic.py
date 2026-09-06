"""M4 semantic recovery tests.

Covers Roadmap M2 Phase 2.3 (heading/paragraph/figure recovery with layer
separation and bundle reference integrity) and M4 (front matter, section
tree, merged paragraphs, tables, equations, footnote references,
bibliography and citations).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from document_model import (
    dump_document,
    validate_bundle_references,
    validate_layer_separation,
)
from document_model.generated import schema_models as generated
from pdf_pipeline.layout import recover_layout_document
from pdf_pipeline.physical import extract_physical_document
from pdf_pipeline.pipeline import (
    build_source_anchors,
    region_lines_from,
    region_texts_from,
)
from pdf_pipeline.render_anchor import build_mapping_bundle
from pdf_pipeline.semantic import recover_semantic_document

if TYPE_CHECKING:
    from document_model.generated.schema_models import (
        LayoutDocument,
        PhysicalDocument,
        SemanticDocument,
    )

FIXTURE_DIR = Path(__file__).resolve().parents[4] / "tests/fixtures/source/latex/build"


def _fixture(name: str) -> bytes:
    path = FIXTURE_DIR / f"{name}.pdf"
    if not path.exists():
        pytest.skip(f"fixture PDF {name} not built; run `just latex-smoke`")
    return path.read_bytes()


def _recover(name: str) -> tuple[PhysicalDocument, LayoutDocument, SemanticDocument]:
    physical = extract_physical_document(_fixture(name))
    layout = recover_layout_document(physical)
    texts = region_texts_from(physical, layout)
    lines = region_lines_from(physical, layout)
    semantic = recover_semantic_document(layout, texts, lines=lines)
    return physical, layout, semantic


def _node(semantic: SemanticDocument, kind: str) -> generated.SemanticNode:
    return next(node for node in semantic.nodes if node.kind == kind)


def _nodes(semantic: SemanticDocument, kind: str) -> list[generated.SemanticNode]:
    return [node for node in semantic.nodes if node.kind == kind]


def test_smoke_produces_headings_and_paragraphs() -> None:
    _, _, semantic = _recover("smoke")
    kinds = {node.kind for node in semantic.nodes}
    assert "HEADING" in kinds
    assert "PARAGRAPH" in kinds
    assert kinds <= {
        "DOCUMENT",
        "FRONT_MATTER",
        "HEADING",
        "PARAGRAPH",
        "FIGURE",
        "FIGURE_CAPTION",
        "EQUATION",
    }


def test_figure_caption_detected_and_related() -> None:
    _, _layout, semantic = _recover("figure-caption")
    kinds = [node.kind for node in semantic.nodes]
    assert kinds.count("FIGURE") == 1
    assert kinds.count("FIGURE_CAPTION") == 1
    caption = _node(semantic, "FIGURE_CAPTION")
    assert isinstance(caption.content, generated.RichText)
    assert "Synthetic raster figure" in caption.content.text
    relation = next(r for r in semantic.relations if r.type == "CAPTION_OF")
    figure = _node(semantic, "FIGURE")
    assert relation.target == figure.id
    assert isinstance(figure.content, generated.FigureContent)
    assert figure.content.label == "1"
    physical_ids = {obj_id for region in _layout.regions for obj_id in region.physicalObjectIds}
    assert not set(figure.content.resources.embeddedImageIds) & physical_ids


def test_table_caption_is_not_figure_caption() -> None:
    _, layout, semantic = _recover("table-heavy")
    assert any(group.kind == "TABLE_BLOCK" for group in layout.groups)
    kinds = [node.kind for node in semantic.nodes]
    assert "TABLE_CAPTION" in kinds
    assert "FIGURE_CAPTION" not in kinds


def test_table_region_becomes_structured_cells() -> None:
    _, _, semantic = _recover("table-heavy")
    table = _node(semantic, "TABLE")
    assert isinstance(table.content, generated.TableContent)
    assert table.content.rows >= 4
    assert table.content.cells
    assert all(cell.content.text.strip() for cell in table.content.cells)
    assert "fallback" in (table.confidence.reason or "")


def test_front_matter_title_author_date() -> None:
    _, _, semantic = _recover("smoke")
    front = _node(semantic, "FRONT_MATTER")
    roles = {node.attributes.get("role") for node in semantic.nodes if node.parentId == front.id}
    assert roles == {"title", "author", "date"}
    title = next(
        node
        for node in semantic.nodes
        if node.parentId == front.id and node.attributes.get("role") == "title"
    )
    assert isinstance(title.content, generated.RichText)
    assert title.content.text == "Smoke Fixture"


def test_section_tree_and_heading_levels() -> None:
    _, _, semantic = _recover("table-heavy")
    section = _node(semantic, "SECTION")
    assert section.attributes["numbering"] == "1"
    heading = next(node for node in semantic.nodes if node.parentId == section.id)
    assert heading.kind == "HEADING"
    assert heading.attributes["level"] == 1
    # The table and its caption live inside the section, not at document root.
    table = _node(semantic, "TABLE")
    assert table.parentId == section.id


def test_merged_paragraphs_carry_all_source_regions() -> None:
    _, layout, semantic = _recover("two-column")
    layout_ids = {region.id for region in layout.regions}
    merged = [
        node
        for node in semantic.nodes
        if node.kind == "PARAGRAPH" and len(node.attributes.get("layoutRegionIds", [])) > 1
    ]
    assert merged, "two-column continuation regions must merge"
    assert any((node.confidence.reason or "").startswith("paragraph merge") for node in merged)
    for node in merged:
        region_ids = node.attributes["layoutRegionIds"]
        assert len(region_ids) > 1
        assert set(region_ids) <= layout_ids


def test_display_equation_recovery_with_number() -> None:
    _, _, semantic = _recover("equation-heavy")
    equations = _nodes(semantic, "EQUATION")
    assert equations
    numbered = [node for node in equations if getattr(node.content, "number", None)]
    assert numbered, "align block must recover its (1) number"
    node = numbered[0]
    content = node.content
    assert isinstance(content, generated.EquationContent)
    assert content.rawText
    assert content.unicodeText
    # Content is never lost even without FORMULA evidence.
    assert any(
        "b2" in equation.content.rawText
        for equation in equations
        if isinstance(equation.content, generated.EquationContent) and equation.content.rawText
    )


def test_inline_equation_marks() -> None:
    _, _, semantic = _recover("equation-heavy")
    marks = [
        mark
        for node in semantic.nodes
        if isinstance(node.content, generated.RichText)
        for mark in node.content.marks
        if mark.type == "INLINE_EQUATION"
    ]
    assert marks, "inline f(x)=x^2 must be marked inside its paragraph"


def test_footnote_references_link_bodies_to_paragraphs() -> None:
    _, _, semantic = _recover("footnote-multicolumn")
    footnotes = _nodes(semantic, "FOOTNOTE")
    assert len(footnotes) == 2
    relations = [r for r in semantic.relations if r.type == "FOOTNOTE_OF"]
    assert len(relations) == 2
    targets = {r.target for r in relations}
    for node in semantic.nodes:
        if not isinstance(node.content, generated.RichText):
            continue
        for mark in node.content.marks:
            if mark.type == "FOOTNOTE_REFERENCE":
                assert mark.targetNodeId in {f.id for f in footnotes}
                assert node.id in targets
                assert mark.end > mark.start


def test_bibliography_entries_and_citations() -> None:
    _, _, semantic = _recover("bibliography")
    assert len(_nodes(semantic, "BIBLIOGRAPHY")) == 1
    entries = _nodes(semantic, "BIBLIOGRAPHY_ENTRY")
    assert [e.attributes.get("label") for e in entries] == ["1", "2"]
    assert all(len(e.attributes["layoutRegionIds"]) > 1 for e in entries), (
        "entry fragments must merge into one node"
    )
    cites = [r for r in semantic.relations if r.type == "CITES"]
    assert len(cites) == 2
    entry_ids = {e.id for e in entries}
    assert {c.target for c in cites} == entry_ids
    citation_marks = [
        mark
        for node in semantic.nodes
        if isinstance(node.content, generated.RichText)
        for mark in node.content.marks
        if mark.type == "CITATION"
    ]
    assert len(citation_marks) == 2
    assert {m.targetNodeId for m in citation_marks} == entry_ids


def test_semantic_carries_no_geometry() -> None:
    physical, layout, semantic = _recover("smoke")
    issues = validate_layer_separation(dump_document(layout), dump_document(semantic))
    assert issues == []
    data = dump_document(semantic)
    for node in data["nodes"]:
        assert "bbox" not in node
        assert "page" not in node["attributes"]
    _ = physical


def test_bundle_references_resolve() -> None:
    physical, layout, semantic = _recover("smoke")
    plb, anchors, ssb = build_source_anchors(physical, layout, semantic)
    assert anchors
    assert ssb
    mapping = build_mapping_bundle(
        semantic,
        source_anchors=anchors,
        source_semantic_bindings=ssb,
        physical_layout_bindings=plb,
        render_anchors=[],
        render_document_id="00000000-0000-0000-0000-000000000000",
    )
    bundle: dict[str, Any] = {
        "physical": dump_document(physical),
        "layout": dump_document(layout),
        "semantic": dump_document(semantic),
        "mappings": dump_document(mapping),
    }
    assert validate_bundle_references(bundle) == []


def test_semantic_recovery_is_deterministic() -> None:
    physical, layout, semantic = _recover("smoke")
    texts = region_texts_from(physical, layout)
    lines = region_lines_from(physical, layout)
    again = recover_semantic_document(layout, texts, lines=lines)
    assert semantic == again


def test_all_regions_become_nodes() -> None:
    physical, layout, semantic = _recover("smoke")
    # Every non-empty content region maps to some semantic node.
    texts = region_texts_from(physical, layout)
    content_regions = {
        region.id
        for region in layout.regions
        if region.id in layout.primaryFlow
        and region.kind in {"TEXT", "TABLE", "FORMULA"}
        and texts.get(region.id, "").strip()
    }
    covered = {
        region_id
        for node in semantic.nodes
        for region_id in node.attributes.get("layoutRegionIds", [])
    }
    assert content_regions <= covered


def test_paper_anatomy_abstract_and_nested_section() -> None:
    _, _, semantic = _recover("paper-anatomy")
    roles = {node.attributes.get("role") for node in semantic.nodes}
    assert "abstract" in roles
    sections = {
        node.attributes.get("numbering"): node
        for node in semantic.nodes
        if node.kind == "SECTION" and node.attributes.get("numbering")
    }
    assert sections["1.1"].parentId == sections["1"].id


def test_cross_page_paragraph_merges_fragments() -> None:
    physical, layout, semantic = _recover("cross-page-paragraph")
    assert len(physical.pages) >= 2
    page_of = {region.id: region.pageId for region in layout.regions}
    merged = [
        node
        for node in semantic.nodes
        if node.kind == "PARAGRAPH" and len(node.attributes.get("layoutRegionIds", [])) > 1
    ]
    assert merged, "cross-page continuation must merge into one paragraph"
    assert any(
        len({page_of[rid] for rid in node.attributes["layoutRegionIds"]}) > 1 for node in merged
    )


def test_unresolved_citation_reports_issue() -> None:
    physical, layout, _semantic = _recover("bibliography")
    texts = region_texts_from(physical, layout)
    host = next(
        region_id
        for region_id, text in texts.items()
        if "[1]" in text and not text.strip().startswith("[")
    )
    texts[host] = f"{texts[host]} [99]"
    broken = recover_semantic_document(layout, texts, lines=region_lines_from(physical, layout))
    messages = [issue.message for issue in (broken.issues.issues if broken.issues else [])]
    assert any("unresolved citation [99]" in message for message in messages)


def test_duplicate_bibliography_entry_reports_issue() -> None:
    physical, layout, _semantic = _recover("bibliography")
    texts = region_texts_from(physical, layout)
    second = next(region_id for region_id, text in texts.items() if text.strip().startswith("[2]"))
    texts[second] = texts[second].replace("[2]", "[1]", 1)
    broken = recover_semantic_document(layout, texts, lines=region_lines_from(physical, layout))
    messages = [issue.message for issue in (broken.issues.issues if broken.issues else [])]
    assert any("duplicate bibliography entry" in message for message in messages)
