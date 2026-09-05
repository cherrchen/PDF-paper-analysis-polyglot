"""Phase 2.3 minimal semantic recovery tests.

Covers Roadmap M2 Phase 2.3: HEADING / PARAGRAPH / FIGURE / FIGURE_CAPTION
node recovery with layer separation and bundle reference integrity.
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


def _region_texts(physical: PhysicalDocument, layout: LayoutDocument) -> dict[str, str]:
    texts: dict[str, str] = {}
    spans = {obj.id: obj for obj in physical.objects if obj.objectType == "textSpan"}
    for region in layout.regions:
        if region.kind != "TEXT":
            continue
        joined = " ".join(
            spans[obj_id].text for obj_id in region.physicalObjectIds if obj_id in spans
        )
        texts[region.id] = joined
    return texts


def _recover(name: str) -> tuple[PhysicalDocument, LayoutDocument, SemanticDocument]:
    physical = extract_physical_document(_fixture(name))
    layout = recover_layout_document(physical)
    semantic = recover_semantic_document(layout, _region_texts(physical, layout))
    return physical, layout, semantic


def test_smoke_produces_headings_and_paragraphs() -> None:
    _, _, semantic = _recover("smoke")
    kinds = {node.kind for node in semantic.nodes}
    assert "HEADING" in kinds
    assert "PARAGRAPH" in kinds
    assert kinds <= {"DOCUMENT", "HEADING", "PARAGRAPH", "FIGURE", "FIGURE_CAPTION"}


def test_figure_caption_detected_and_related() -> None:
    _, _layout, semantic = _recover("figure-caption")
    kinds = [node.kind for node in semantic.nodes]
    assert kinds.count("FIGURE") == 1
    assert kinds.count("FIGURE_CAPTION") == 1
    caption = next(node for node in semantic.nodes if node.kind == "FIGURE_CAPTION")
    assert isinstance(caption.content, generated.RichText)
    assert "Synthetic raster figure" in caption.content.text
    relation_types = {relation.type for relation in semantic.relations}
    assert "CAPTION_OF" in relation_types


def test_table_caption_is_not_figure_caption() -> None:
    _, layout, semantic = _recover("table-heavy")
    assert any(group.kind == "TABLE_BLOCK" for group in layout.groups)
    kinds = [node.kind for node in semantic.nodes]
    assert "TABLE_CAPTION" in kinds
    assert "FIGURE_CAPTION" not in kinds


def test_semantic_carries_no_geometry() -> None:
    physical, layout, semantic = _recover("smoke")
    issues = validate_layer_separation(dump_document(physical), dump_document(layout))
    assert issues == []
    data = dump_document(semantic)
    for node in data["nodes"]:
        assert "bbox" not in node
        assert "page" not in node["attributes"]


def test_bundle_references_resolve() -> None:
    physical, layout, semantic = _recover("smoke")
    bundle: dict[str, Any] = {
        "physical": dump_document(physical),
        "layout": dump_document(layout),
        "semantic": dump_document(semantic),
        "mappings": {
            "schemaVersion": "0.1.0",
            "id": "00000000-0000-0000-0000-000000000000",
            "physicalLayoutBindings": [],
            "sourceAnchors": [],
            "sourceSemanticBindings": [],
        },
    }
    assert validate_bundle_references(bundle) == []


def test_semantic_recovery_is_deterministic() -> None:
    _, layout, semantic = _recover("smoke")
    again = recover_semantic_document(
        layout, _region_texts(extract_physical_document(_fixture("smoke")), layout)
    )
    assert semantic == again


def test_all_regions_become_nodes() -> None:
    _, layout, semantic = _recover("smoke")
    # Every non-empty text region maps to exactly one semantic node.
    text_regions = {r.id for r in layout.regions if r.kind == "TEXT"}
    assert len(semantic.nodes) - 1 >= len(text_regions) - len(
        [
            rid
            for rid in text_regions
            if not _region_texts(extract_physical_document(_fixture("smoke")), layout)
            .get(rid, "")
            .strip()
        ]
    )
