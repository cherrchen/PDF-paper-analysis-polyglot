"""Phase 4.9 semantic validator unit tests.

Each test takes a real recovered fixture, breaks it exactly one way, and
asserts the validator reports that break. A validator that never fires is
decoration; these pin the detection behavior the M4 exit gate relies on.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from document_model.generated import schema_models as generated
from pdf_pipeline.ids import stable_uuid
from pdf_pipeline.layout import recover_layout_document
from pdf_pipeline.physical import extract_physical_document
from pdf_pipeline.pipeline import region_texts_from
from pdf_pipeline.sem_validate import validate_semantic_recovery
from pdf_pipeline.semantic import recover_semantic_document

if TYPE_CHECKING:
    from document_model.generated.schema_models import (
        LayoutDocument,
        PhysicalDocument,
        SemanticDocument,
    )

    _Recovered = tuple[PhysicalDocument, LayoutDocument, SemanticDocument, dict[str, str]]

FIXTURE_DIR = Path(__file__).resolve().parents[4] / "tests/fixtures/source/latex/build"


def _recover(name: str) -> _Recovered:
    pdf = FIXTURE_DIR / f"{name}.pdf"
    if not pdf.exists():
        pytest.skip(f"{name} fixture PDF not built; run `just latex-smoke`")
    physical = extract_physical_document(pdf.read_bytes())
    layout = recover_layout_document(physical)
    texts = region_texts_from(physical, layout)
    semantic = recover_semantic_document(layout, texts)
    return physical, layout, semantic, texts


def _categories(
    layout: LayoutDocument, semantic: SemanticDocument, texts: dict[str, str]
) -> set[tuple[str, str]]:
    return {
        (issue.category, issue.severity)
        for issue in validate_semantic_recovery(semantic, layout, texts)
    }


def _replace_node(semantic: SemanticDocument, node_id: str, **updates: object) -> SemanticDocument:
    nodes = [
        node.model_copy(update=updates) if node.id == node_id else node for node in semantic.nodes
    ]
    return semantic.model_copy(update={"nodes": nodes})


def test_clean_recovery_reports_nothing() -> None:
    _physical, layout, semantic, texts = _recover("smoke")
    assert validate_semantic_recovery(semantic, layout, texts) == []


def test_unreachable_node_is_orphan_error() -> None:
    _physical, layout, semantic, texts = _recover("smoke")
    paragraph = next(node for node in semantic.nodes if node.kind == "PARAGRAPH")
    # Detach the paragraph from every parent's children list.
    nodes = [
        node.model_copy(update={"children": [c for c in node.children if c != paragraph.id]})
        for node in semantic.nodes
    ]
    broken = semantic.model_copy(update={"nodes": nodes})
    assert ("SECTION_STRUCTURE", "ERROR") in _categories(layout, broken, texts)


def test_unbound_paragraph_is_mapping_error() -> None:
    _physical, layout, semantic, texts = _recover("smoke")
    paragraph = next(node for node in semantic.nodes if node.kind == "PARAGRAPH")
    broken = _replace_node(
        semantic,
        paragraph.id,
        attributes={**paragraph.attributes, "layoutRegionIds": []},
    )
    assert ("SOURCE_MAPPING", "ERROR") in _categories(layout, broken, texts)


def test_dangling_relation_target_is_warning() -> None:
    _physical, layout, semantic, texts = _recover("smoke")
    paragraph = next(node for node in semantic.nodes if node.kind == "PARAGRAPH")
    relation = generated.SemanticRelation(
        id=stable_uuid(semantic.id, "test-rel"),
        type="CITES",
        source=paragraph.id,
        target=stable_uuid(semantic.id, "ghost-node"),
        confidence=0.5,
        provenanceIds=[],
    )
    broken = semantic.model_copy(update={"relations": [*semantic.relations, relation]})
    assert ("CITATION_RESOLUTION", "WARNING") in _categories(layout, broken, texts)


def test_caption_without_relation_is_warning() -> None:
    _physical, layout, semantic, texts = _recover("figure-caption")
    assert ("FIGURE_RECOVERY", "WARNING") not in _categories(layout, semantic, texts)
    captions = [r for r in semantic.relations if r.type == "CAPTION_OF"]
    assert captions, "figure-caption must produce CAPTION_OF"
    broken = semantic.model_copy(
        update={"relations": [r for r in semantic.relations if r not in captions]}
    )
    assert ("FIGURE_RECOVERY", "WARNING") in _categories(layout, broken, texts)


def test_double_coverage_is_error() -> None:
    _physical, layout, semantic, texts = _recover("smoke")
    paragraph = next(node for node in semantic.nodes if node.kind == "PARAGRAPH")
    other = next(
        node for node in semantic.nodes if node.kind == "PARAGRAPH" and node.id != paragraph.id
    )
    shared = list(other.attributes["layoutRegionIds"]) + list(
        paragraph.attributes["layoutRegionIds"]
    )
    broken = _replace_node(
        semantic, other.id, attributes={**other.attributes, "layoutRegionIds": shared}
    )
    assert ("SOURCE_MAPPING", "ERROR") in _categories(layout, broken, texts)


def test_heading_level_jump_is_warning() -> None:
    _physical, layout, semantic, texts = _recover("paper-anatomy")
    subsection = next(
        node
        for node in semantic.nodes
        if node.kind == "HEADING" and node.attributes.get("level") == 2
    )
    broken = _replace_node(
        semantic, subsection.id, attributes={**subsection.attributes, "level": 4}
    )
    assert ("SECTION_STRUCTURE", "WARNING") in _categories(layout, broken, texts)


def test_missing_coverage_reports_mapping_issue() -> None:
    _physical, layout, semantic, texts = _recover("smoke")
    paragraph = next(node for node in semantic.nodes if node.kind == "PARAGRAPH")
    nodes = [
        node.model_copy(
            update={"children": [child for child in node.children if child != paragraph.id]}
        )
        for node in semantic.nodes
        if node.id != paragraph.id
    ]
    broken = semantic.model_copy(update={"nodes": nodes})
    categories = _categories(layout, broken, texts)
    assert ("SOURCE_MAPPING", "ERROR") in categories or ("SOURCE_MAPPING", "WARNING") in categories


def test_table_caption_without_relation_uses_table_recovery() -> None:
    _physical, layout, semantic, texts = _recover("table-heavy")
    captions = [relation for relation in semantic.relations if relation.type == "CAPTION_OF"]
    broken = semantic.model_copy(
        update={
            "relations": [relation for relation in semantic.relations if relation not in captions]
        }
    )
    assert ("TABLE_RECOVERY", "WARNING") in _categories(layout, broken, texts)
