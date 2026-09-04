"""Phase 1.2 validation: PhysicalDocument schema, geometry, ID reconciliation."""

from __future__ import annotations

from typing import Any

import document_model.generated.schema_models as m
import pytest
from document_model import dump_document, load_document, new_id
from pydantic import ValidationError


@pytest.mark.unit
def test_physical_document_serialization_roundtrip(physical_data: dict[str, Any]) -> None:
    doc = load_document("physical-document", physical_data)
    dumped = dump_document(doc)
    assert dumped == physical_data, "serialization must be stable"


@pytest.mark.unit
def test_repeated_parsing_produces_stable_geometry(physical_data: dict[str, Any]) -> None:
    first = m.PhysicalDocument.model_validate(physical_data)
    second = m.PhysicalDocument.model_validate(dump_document(first))
    assert first.pages[0].geometry == second.pages[0].geometry
    assert [p.objectIds for p in first.pages] == [p.objectIds for p in second.pages]


@pytest.mark.unit
def test_ids_reconcilable_via_source_fingerprint(physical_data: dict[str, Any]) -> None:
    doc = m.PhysicalDocument.model_validate(physical_data)
    assert doc.sourceFingerprint == "sha256:fixture"
    reprinted = physical_data.copy()
    reprinted["id"] = new_id()
    other = m.PhysicalDocument.model_validate(reprinted)
    assert other.id != doc.id
    assert other.sourceFingerprint == doc.sourceFingerprint


@pytest.mark.unit
def test_page_geometry_uses_canonical_space(physical_data: dict[str, Any]) -> None:
    doc = m.PhysicalDocument.model_validate(physical_data)
    page = doc.pages[0]
    assert page.geometry.widthPt == 612
    assert page.geometry.heightPt == 792
    assert page.geometry.rotation == 0


@pytest.mark.unit
def test_text_span_coordinates_in_points(physical_data: dict[str, Any]) -> None:
    doc = m.PhysicalDocument.model_validate(physical_data)
    spans = [o for o in doc.objects if o.objectType == "textSpan"]
    for span in spans:
        rect = span.geometry
        assert rect.kind == "rect"
        assert 0 <= rect.x <= 612
        assert 0 <= rect.y <= 792


@pytest.mark.unit
def test_physical_layer_forbids_semantic_pollution(physical_data: dict[str, Any]) -> None:
    polluted = dict(physical_data)
    polluted["objects"] = [
        *physical_data["objects"],
        {
            "objectType": "textSpan",
            "id": new_id(),
            "pageId": physical_data["pages"][0]["id"],
            "text": "Methods",
            "geometry": {"kind": "rect", "x": 1, "y": 1, "width": 5, "height": 5},
            "section": "methods",  # semantic key must be rejected
        },
    ]
    with pytest.raises(ValidationError):
        m.PhysicalDocument.model_validate(polluted)
