"""Phase 1.5 validation: SemanticDocument structure independence."""

from __future__ import annotations

from typing import Any

import document_model.generated.schema_models as m
import pytest
from document_model import dump_document, load_document

type Json = dict[str, Json] | list[Json] | str | int | float | bool | None


@pytest.mark.unit
def test_semantic_document_roundtrip(semantic_data: dict[str, Any]) -> None:
    doc = load_document("semantic-document", semantic_data)
    assert dump_document(doc) == semantic_data


@pytest.mark.unit
def test_required_node_kinds_present(semantic_data: dict[str, Any]) -> None:
    doc = m.SemanticDocument.model_validate(semantic_data)
    kinds = {n.kind for n in doc.nodes}
    for required in (
        "DOCUMENT",
        "HEADING",
        "PARAGRAPH",
        "FIGURE",
        "FIGURE_CAPTION",
        "FOOTNOTE",
        "BIBLIOGRAPHY_ENTRY",
    ):
        assert required in kinds, f"missing node kind {required}"


@pytest.mark.unit
def test_semantic_layer_survives_pdf_information_deletion(semantic_data: dict[str, Any]) -> None:
    """Export independently: no layout geometry keys anywhere in the payload."""

    forbidden = {"pageId", "bbox", "column", "fontSize", "layoutRegionId"}

    def walk(value: Json) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                # TableCell.column indexes a table grid, not a layout column.
                if key == "column" and "row" in value and "rowSpan" in value:
                    walk(child)
                    continue
                assert key not in forbidden, key
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(semantic_data)


@pytest.mark.unit
def test_section_heading_independence(semantic_data: dict[str, Any]) -> None:
    doc = m.SemanticDocument.model_validate(semantic_data)
    headings = [n for n in doc.nodes if n.kind == "HEADING"]
    assert headings, "heading must exist as its own node"
    heading = headings[0]
    heading_content = heading.content
    assert isinstance(heading_content, m.RichText)
    assert heading_content.text.startswith("1."), (
        "heading is a semantic block, translatable on its own"
    )


@pytest.mark.unit
def test_caption_and_footnote_relations(semantic_data: dict[str, Any]) -> None:
    doc = m.SemanticDocument.model_validate(semantic_data)
    types = {r.type for r in doc.relations}
    assert "CAPTION_OF" in types
    assert "FOOTNOTE_OF" in types
    assert "CITES" in types


@pytest.mark.unit
def test_citation_mark_targets_resolved_node(semantic_data: dict[str, Any]) -> None:
    doc = m.SemanticDocument.model_validate(semantic_data)
    node_ids = {n.id for n in doc.nodes}
    for node in doc.nodes:
        content = node.content
        if isinstance(content, m.RichText):
            for mark in content.marks:
                if mark.type == "CITATION":
                    assert mark.targetNodeId in node_ids


@pytest.mark.unit
def test_semantic_layer_rejects_geometry_attributes() -> None:
    """The attribute bag is open by schema, so the layer validator is the guard."""
    from document_model import validate_layer_separation

    geometry_node: dict[str, Any] = {
        "id": "01J5M1FXTRES0AAAAAAA0GEO00",
        "kind": "PARAGRAPH",
        "children": [],
        "content": {"text": "hello", "marks": []},
        "attributes": {"bbox": [1, 2, 3, 4]},
        "confidence": {"score": 1.0},
        "provenanceIds": [],
    }
    issues = validate_layer_separation({"regions": []}, {"nodes": [geometry_node]})
    assert any("bbox" in issue for issue in issues)
