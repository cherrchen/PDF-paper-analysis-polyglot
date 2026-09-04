"""Phase 1.4 validation: LayoutDocument regions, bands, reading flow."""

from __future__ import annotations

from typing import Any

import document_model.generated.schema_models as m
import pytest
from document_model import dump_document, load_document
from pydantic import ValidationError


@pytest.mark.unit
def test_layout_document_roundtrip(layout_data: dict[str, Any]) -> None:
    doc = load_document("layout-document", layout_data)
    assert dump_document(doc) == layout_data


@pytest.mark.unit
def test_describes_columns_and_spanning_figure(layout_data: dict[str, Any]) -> None:
    doc = m.LayoutDocument.model_validate(layout_data)
    modes = {band.layoutMode for band in doc.bands}
    assert "MULTI_COLUMN" in modes
    assert "FULL_WIDTH" in modes
    figure = next(r for r in doc.regions if r.kind == "FIGURE")
    geometry = figure.geometry
    assert isinstance(geometry, m.Rect)
    assert geometry.width > geometry.height
    figure_group = next(g for g in doc.groups if g.kind == "FIGURE_BLOCK")
    assert len(set(figure_group.memberIds)) >= 2


@pytest.mark.unit
def test_reading_flow_graph_is_source_of_truth(layout_data: dict[str, Any]) -> None:
    doc = m.LayoutDocument.model_validate(layout_data)
    # primary flow must be derivable from graph edges
    edges = {(e.source, e.target) for e in doc.readingFlow.edges}
    for a, b in zip(doc.primaryFlow, doc.primaryFlow[1:], strict=False):
        assert (a, b) in edges, f"primary flow edge {a} -> {b} missing from graph"


@pytest.mark.unit
def test_footnotes_stay_out_of_primary_flow(layout_data: dict[str, Any]) -> None:
    doc = m.LayoutDocument.model_validate(layout_data)
    footnote = next(r for r in doc.regions if r.kind == "FOOTNOTE")
    assert footnote.id not in doc.primaryFlow
    assert footnote.id in doc.readingFlow.nodes


@pytest.mark.unit
def test_regions_reference_physical_objects(
    layout_data: dict[str, Any], physical_data: dict[str, Any]
) -> None:
    doc = m.LayoutDocument.model_validate(layout_data)
    physical_ids = {str(o["id"]) for o in physical_data["objects"]}
    for region in doc.regions:
        assert region.physicalObjectIds, f"region {region.id} has no physical objects"
        for obj_id in region.physicalObjectIds:
            assert obj_id in physical_ids


@pytest.mark.unit
def test_layout_layer_forbids_semantic_labels(layout_data: dict[str, Any]) -> None:
    polluted = dict(layout_data)
    polluted["regions"] = [
        *layout_data["regions"],
        {
            "id": "01J5M1FXTRES0AAAAAAA0BADRG",
            "pageId": layout_data["pages"][0]["pageId"],
            "geometry": {"kind": "rect", "x": 0, "y": 0, "width": 1, "height": 1},
            "kind": "TEXT",
            "childIds": [],
            "physicalObjectIds": [],
            "labels": [],
            "confidence": {"score": 1.0},
            "provenanceIds": [],
            "method_section": True,  # semantic flag must be rejected
        },
    ]
    with pytest.raises(ValidationError):
        m.LayoutDocument.model_validate(polluted)
