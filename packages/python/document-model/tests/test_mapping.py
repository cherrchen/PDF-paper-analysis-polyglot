"""Phase 1.6 validation: Mapping schema many-to-many scenarios."""

from __future__ import annotations

from copy import deepcopy
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
    """Figure + caption regions share an anchor that binds two semantic nodes."""
    doc = m.MappingBundle.model_validate(mapping_data)
    anchors_by_id = {anchor.id: anchor for anchor in doc.sourceAnchors}
    region_nodes: dict[str, set[str]] = {}
    node_regions: dict[str, set[str]] = {}
    for binding in doc.sourceSemanticBindings:
        regions: set[str] = set()
        for anchor_id in binding.sourceAnchorIds:
            anchor = anchors_by_id[anchor_id]
            regions.update(fragment.layoutRegionId for fragment in anchor.fragments)
        node_regions.setdefault(binding.semanticNodeId, set()).update(regions)
        for region in regions:
            region_nodes.setdefault(region, set()).add(binding.semanticNodeId)

    visited: set[str] = set()
    found_many_to_many = False
    for start in node_regions:
        if start in visited:
            continue
        stack: list[tuple[str, str]] = [("n", start)]
        seen: set[tuple[str, str]] = set()
        component_nodes: set[str] = set()
        component_regions: set[str] = set()
        while stack:
            kind, ident = stack.pop()
            key = (kind, ident)
            if key in seen:
                continue
            seen.add(key)
            if kind == "n":
                visited.add(ident)
                component_nodes.add(ident)
                stack.extend(("r", region) for region in node_regions[ident])
            else:
                component_regions.add(ident)
                stack.extend(("n", node) for node in region_nodes[ident])
        if len(component_nodes) >= 2 and len(component_regions) >= 2:
            found_many_to_many = True
            break
    assert found_many_to_many, "fixture must include a connected N-layout to N-semantic mapping"


@pytest.mark.unit
def test_cross_page_paragraph_uses_two_pages(
    mapping_data: dict[str, Any],
    layout_data: dict[str, Any],
    physical_data: dict[str, Any],
) -> None:
    """Cross-page paragraph: two regions on two pages, two physical spans on two pages."""
    mapping = m.MappingBundle.model_validate(mapping_data)
    layout = m.LayoutDocument.model_validate(layout_data)
    physical = m.PhysicalDocument.model_validate(physical_data)
    page_by_region = {region.id: region.pageId for region in layout.regions}
    objects_by_id = {obj.id: obj for obj in physical.objects}
    regions_by_id = {region.id: region for region in layout.regions}
    anchors_by_id = {anchor.id: anchor for anchor in mapping.sourceAnchors}

    found = False
    for binding in mapping.sourceSemanticBindings:
        region_pages: set[str] = set()
        object_pages: set[str] = set()
        for anchor_id in binding.sourceAnchorIds:
            for fragment in anchors_by_id[anchor_id].fragments:
                region_pages.add(page_by_region[fragment.layoutRegionId])
                region = regions_by_id[fragment.layoutRegionId]
                for obj_id in region.physicalObjectIds:
                    object_pages.add(objects_by_id[obj_id].pageId)
        if len(region_pages) >= 2 and len(object_pages) >= 2:
            found = True
            break
    assert found, "cross-page paragraph must use two pages for both regions and physical objects"


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
    evidence_data: dict[str, Any],
) -> None:
    bundle = {
        "physical": physical_data,
        "layout": layout_data,
        "semantic": semantic_data,
        "mappings": mapping_data,
        "evidence": evidence_data,
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


@pytest.mark.unit
def test_bundle_reference_validator_detects_unknown_root(
    physical_data: dict[str, Any],
    layout_data: dict[str, Any],
    semantic_data: dict[str, Any],
    mapping_data: dict[str, Any],
) -> None:
    broken = dict(semantic_data)
    broken["rootId"] = "01J5M1FXTRES0AAAAAAA0GHOST"
    bundle = {
        "physical": physical_data,
        "layout": layout_data,
        "semantic": broken,
        "mappings": mapping_data,
    }
    issues = validate_bundle_references(bundle)
    assert any("unknown rootId" in issue for issue in issues)


@pytest.mark.unit
def test_bundle_reference_validator_detects_unknown_relation_target(
    physical_data: dict[str, Any],
    layout_data: dict[str, Any],
    semantic_data: dict[str, Any],
    mapping_data: dict[str, Any],
) -> None:
    broken = dict(semantic_data)
    relations = list(semantic_data["relations"])
    first = dict(relations[0])
    first["target"] = "01J5M1FXTRES0AAAAAAA0GHOST"
    broken["relations"] = [first, *relations[1:]]
    bundle = {
        "physical": physical_data,
        "layout": layout_data,
        "semantic": broken,
        "mappings": mapping_data,
    }
    issues = validate_bundle_references(bundle)
    assert any("unknown target" in issue for issue in issues)


@pytest.mark.unit
def test_bundle_reference_validator_detects_duplicate_ids(
    physical_data: dict[str, Any],
    layout_data: dict[str, Any],
    semantic_data: dict[str, Any],
    mapping_data: dict[str, Any],
) -> None:
    broken = dict(physical_data)
    objects = list(physical_data["objects"])
    broken["objects"] = [objects[0], objects[0], *objects[1:]]
    bundle = {
        "physical": broken,
        "layout": layout_data,
        "semantic": semantic_data,
        "mappings": mapping_data,
    }
    issues = validate_bundle_references(bundle)
    assert any("duplicate id" in issue for issue in issues)


@pytest.mark.unit
def test_bundle_reference_validator_checks_physical_page_membership(
    physical_data: dict[str, Any],
    layout_data: dict[str, Any],
    semantic_data: dict[str, Any],
    mapping_data: dict[str, Any],
) -> None:
    broken = deepcopy(physical_data)
    broken["pages"][0]["objectIds"].append("01J5M1FXTRES0AAAAAAA0GHOST")
    issues = validate_bundle_references(
        {
            "physical": broken,
            "layout": layout_data,
            "semantic": semantic_data,
            "mappings": mapping_data,
        }
    )
    assert any("physical page" in issue and "unknown object" in issue for issue in issues)


@pytest.mark.unit
def test_bundle_reference_validator_checks_layout_containers_and_flow(
    physical_data: dict[str, Any],
    layout_data: dict[str, Any],
    semantic_data: dict[str, Any],
    mapping_data: dict[str, Any],
) -> None:
    ghost = "01J5M1FXTRES0AAAAAAA0GHOST"
    broken = deepcopy(layout_data)
    broken["pages"][0]["regionIds"].append(ghost)
    broken["pages"][0]["bandIds"].append(ghost)
    broken["bands"][0]["columnIds"].append(ghost)
    broken["columns"][0]["regionIds"].append(ghost)
    broken["readingFlow"]["nodes"].append(ghost)
    broken["readingFlow"]["edges"][0]["target"] = ghost
    broken["primaryFlow"].append(ghost)
    issues = validate_bundle_references(
        {
            "physical": physical_data,
            "layout": broken,
            "semantic": semantic_data,
            "mappings": mapping_data,
        }
    )
    for fragment in (
        "unknown region",
        "unknown band",
        "unknown column",
        "unknown node",
        "unknown target",
        "primary flow",
    ):
        assert any(fragment in issue for issue in issues), fragment


@pytest.mark.unit
def test_bundle_reference_validator_checks_evidence_references(
    physical_data: dict[str, Any],
    layout_data: dict[str, Any],
    semantic_data: dict[str, Any],
    mapping_data: dict[str, Any],
    evidence_data: dict[str, Any],
) -> None:
    ghost = "01J5M1FXTRES0AAAAAAA0GHOST"
    broken_evidence = deepcopy(evidence_data)
    broken_evidence["candidates"][0]["pageId"] = ghost
    broken_evidence["candidates"][-1]["parentId"] = ghost
    broken_layout = deepcopy(layout_data)
    broken_layout["regions"][0]["labels"][0]["evidenceIds"] = [ghost]
    issues = validate_bundle_references(
        {
            "physical": physical_data,
            "layout": broken_layout,
            "semantic": semantic_data,
            "mappings": mapping_data,
            "evidence": broken_evidence,
        }
    )
    assert any("unknown pageId" in issue for issue in issues)
    assert any("unknown parentId" in issue for issue in issues)
    assert any("unknown evidence" in issue for issue in issues)


@pytest.mark.unit
def test_bundle_reference_validator_checks_document_inline_and_provenance_refs(
    physical_data: dict[str, Any],
    layout_data: dict[str, Any],
    semantic_data: dict[str, Any],
    mapping_data: dict[str, Any],
) -> None:
    ghost = "01J5M1FXTRES0AAAAAAA0GHOST"
    broken_layout = deepcopy(layout_data)
    broken_layout["physicalDocumentId"] = ghost
    broken_semantic = deepcopy(semantic_data)
    broken_semantic["layoutDocumentId"] = ghost
    paragraph = next(node for node in broken_semantic["nodes"] if node["kind"] == "PARAGRAPH")
    paragraph["content"]["marks"][0]["targetNodeId"] = ghost
    broken_mapping = deepcopy(mapping_data)
    broken_mapping["sourceAnchors"][0]["provenanceIds"] = [ghost]
    issues = validate_bundle_references(
        {
            "physical": physical_data,
            "layout": broken_layout,
            "semantic": broken_semantic,
            "mappings": broken_mapping,
        }
    )
    assert any("physicalDocumentId" in issue for issue in issues)
    assert any("layoutDocumentId" in issue for issue in issues)
    assert any("inline mark" in issue for issue in issues)
    assert any("unknown provenance" in issue for issue in issues)
