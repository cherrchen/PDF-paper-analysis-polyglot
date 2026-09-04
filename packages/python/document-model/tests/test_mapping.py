"""Phase 1.6 validation: Mapping schema many-to-many scenarios."""

from __future__ import annotations

from typing import Any

import document_model.generated.schema_models as m
import pytest
from document_model import dump_document, load_document, validate_bundle_references


@pytest.mark.unit
def test_mapping_bundle_roundtrip(mapping_data: dict[str, Any]) -> None:
    doc = load_document("mapping", mapping_data)
    assert dump_document(doc) == mapping_data


@pytest.mark.unit
def test_n_layout_to_one_semantic(mapping_data: dict[str, Any]) -> None:
    """Column-spanning paragraph: left + right regions -> one paragraph node."""
    doc = m.MappingBundle.model_validate(mapping_data)
    anchors_by_id = {a.id: a for a in doc.sourceAnchors}

    def regions_of(binding: m.SourceSemanticBinding) -> set[str]:
        return {
            f.layoutRegionId
            for anchor_id in binding.sourceAnchorIds
            if (anchor := anchors_by_id.get(anchor_id)) is not None
            for f in anchor.fragments
        }

    span_binding = next(b for b in doc.sourceSemanticBindings if len(regions_of(b)) >= 2)
    assert len(span_binding.sourceAnchorIds) >= 1
    anchor_ids = set(span_binding.sourceAnchorIds)
    fragments = [f for a in doc.sourceAnchors if a.id in anchor_ids for f in a.fragments]
    region_ids = {f.layoutRegionId for f in fragments}
    assert len(region_ids) >= 2, "spanning paragraph must anchor multiple layout regions"


@pytest.mark.unit
def test_one_layout_to_n_semantic(mapping_data: dict[str, Any]) -> None:
    """One text block splits into heading + paragraph: same region, two nodes."""
    doc = m.MappingBundle.model_validate(mapping_data)
    by_node: dict[str, set[str]] = {}
    for binding in doc.sourceSemanticBindings:
        for anchor_id in binding.sourceAnchorIds:
            anchor = next(a for a in doc.sourceAnchors if a.id == anchor_id)
            for fragment in anchor.fragments:
                by_node.setdefault(binding.semanticNodeId, set()).add(fragment.layoutRegionId)
    # find two different nodes sharing a region
    region_to_nodes: dict[str, set[str]] = {}
    for node_id, regions in by_node.items():
        for region in regions:
            region_to_nodes.setdefault(region, set()).add(node_id)
    assert any(len(nodes) >= 2 for nodes in region_to_nodes.values()), (
        "one layout region must be able to anchor multiple semantic nodes"
    )


@pytest.mark.unit
def test_n_layout_to_n_semantic(mapping_data: dict[str, Any]) -> None:
    """Cross-page paragraph: two anchors -> one node, node reuses region family."""
    doc = m.MappingBundle.model_validate(mapping_data)
    cross_page = [b for b in doc.sourceSemanticBindings if len(b.sourceAnchorIds) >= 2]
    assert cross_page, "fixture must include a multi-anchor binding"


@pytest.mark.unit
def test_physical_layout_binding_is_authoritative(
    mapping_data: dict[str, Any], physical_data: dict[str, Any]
) -> None:
    doc = m.MappingBundle.model_validate(mapping_data)
    object_ids = {str(o["id"]) for o in physical_data["objects"]}
    for binding in doc.physicalLayoutBindings:
        for obj_id in binding.physicalObjectIds:
            assert obj_id in object_ids


@pytest.mark.unit
def test_bundle_reference_validator_accepts_fixture_bundle(
    physical_data: dict[str, Any],
    layout_data: dict[str, Any],
    semantic_data: dict[str, Any],
    mapping_data: dict[str, Any],
) -> None:
    bundle = {
        "physical": physical_data,
        "layout": layout_data,
        "semantic": semantic_data,
        "mappings": mapping_data,
    }
    assert validate_bundle_references(bundle) == []


@pytest.mark.unit
def test_bundle_reference_validator_detects_dangling_ids(
    physical_data: dict[str, Any],
    layout_data: dict[str, Any],
    semantic_data: dict[str, Any],
    mapping_data: dict[str, Any],
) -> None:
    broken = dict(mapping_data)
    broken["sourceSemanticBindings"] = [
        *mapping_data["sourceSemanticBindings"],
        {
            "id": "01J5M1FXTRES0AAAAAAA0SSB99",
            "semanticNodeId": "01J5M1FXTRES0AAAAAAA0GHOST",
            "sourceAnchorIds": [],
        },
    ]
    bundle = {
        "physical": physical_data,
        "layout": layout_data,
        "semantic": semantic_data,
        "mappings": broken,
    }
    issues = validate_bundle_references(bundle)
    assert any("unknown node" in issue for issue in issues)
