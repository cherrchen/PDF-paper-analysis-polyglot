"""Cross-layer validators for the canonical document contracts.

These checks encode the permanent architecture boundaries:

- Semantic layer must never carry layout geometry (page, bbox, column).
- Layout layer must never carry paper semantics.
- ID references inside a bundle must resolve.
"""

from __future__ import annotations

import re
from typing import Any

_GEOMETRY_KEYS = {"page", "bbox", "column", "pageBreak", "pageSize", "font", "fontSize"}
_GEOMETRY_PATTERNS = (
    re.compile(r"(?i)[^a-z]bbox"),
    re.compile(r"(?i)\bbbox\b"),
)

_SEMANTIC_KEYS_IN_LAYOUT = {
    "section",
    "heading_level",
    "citation",
    "bibliography",
    "translation",
    "method_section",
    "paragraph",
}

_SEMANTIC_LABELS = {"SECTION", "CITATION", "BIBLIOGRAPHY"}


def _is_geometry_key(key: str) -> bool:
    return key.lower() in _GEOMETRY_KEYS or any(p.search(key) for p in _GEOMETRY_PATTERNS)


def validate_layer_separation(
    layout_document: dict[str, Any], semantic_document: dict[str, Any]
) -> list[str]:
    """Return violations of the layer responsibility boundaries.

    Layout regions must only describe visual structure. Semantic nodes and
    their attributes must only describe logical structure.
    """
    issues: list[str] = []

    for region in layout_document.get("regions", []):
        region_id = region.get("id")
        issues.extend(
            f"layout region {region_id}: semantic key {key!r} not allowed"
            for key in region
            if key.lower() in _SEMANTIC_KEYS_IN_LAYOUT
        )
        issues.extend(
            f"layout region {region_id}: semantic label {label.get('label')!r} not allowed"
            for label in region.get("labels", [])
            if label.get("label") in _SEMANTIC_LABELS
        )

    for node in semantic_document.get("nodes", []):
        node_id = node.get("id")
        issues.extend(
            f"semantic node {node_id}: geometry key {key!r} not allowed"
            for key in node
            if _is_geometry_key(key)
        )
        issues.extend(
            f"semantic node {node_id}: geometry attribute {key!r} not allowed"
            for key in node.get("attributes", {})
            if _is_geometry_key(key)
        )

    return issues


def _collect_ids(document: dict[str, Any], key: str) -> list[str]:
    return [item["id"] for item in document.get(key, []) if "id" in item]


def _duplicate_issues(ids: list[str], label: str) -> list[str]:
    seen: set[str] = set()
    issues: list[str] = []
    for value in ids:
        if value in seen:
            issues.append(f"{label}: duplicate id {value}")
        seen.add(value)
    return issues


def _unknown_ref(ref: str | None, known: set[str], message: str) -> list[str]:
    if ref is None or ref in known:
        return []
    return [message]


def _check_layout_references(
    layout: dict[str, Any], page_ids: set[str], object_ids: set[str]
) -> list[str]:
    issues: list[str] = []
    region_ids = {region["id"] for region in layout.get("regions", []) if "id" in region}
    for region in layout.get("regions", []):
        if region.get("pageId") not in page_ids:
            issues.append(
                f"layout region {region.get('id')}: unknown pageId {region.get('pageId')}"
            )
        issues.extend(
            f"layout region {region.get('id')}: unknown physical object {obj_id}"
            for obj_id in region.get("physicalObjectIds", [])
            if obj_id not in object_ids
        )
        issues.extend(
            f"layout region {region.get('id')}: unknown child {child}"
            for child in region.get("childIds", [])
            if child not in region_ids
        )
    for group in layout.get("groups", []):
        issues.extend(
            f"layout group {group.get('id')}: unknown member {member}"
            for member in group.get("memberIds", [])
            if member not in region_ids
        )
        page_id = group.get("pageId")
        if page_id is not None and page_id not in page_ids:
            issues.append(f"layout group {group.get('id')}: unknown pageId {page_id}")
    return issues


def _check_semantic_tree(semantic: dict[str, Any], node_ids: set[str]) -> list[str]:
    issues: list[str] = []
    root_id = semantic.get("rootId")
    if root_id is None:
        issues.append("semantic document: missing rootId")
    elif root_id not in node_ids:
        issues.append(f"semantic document: unknown rootId {root_id}")

    children_of: dict[str, list[str]] = {}
    parent_of: dict[str, Any] = {}
    for node in semantic.get("nodes", []):
        node_id = node.get("id")
        parent = node.get("parentId")
        parent_of[node_id] = parent
        if parent is not None and parent not in node_ids:
            issues.append(f"semantic node {node_id}: unknown parent {parent}")
        children = list(node.get("children", []))
        children_of[node_id] = children
        issues.extend(
            f"semantic node {node_id}: unknown child {child}"
            for child in children
            if child not in node_ids
        )

    for node_id, children in children_of.items():
        issues.extend(
            f"semantic node {child}: parentId {parent_of.get(child)!r} "
            f"does not match parent {node_id} that lists it as a child"
            for child in children
            if parent_of.get(child) != node_id
        )
    for node_id, parent in parent_of.items():
        if parent is None:
            continue
        if node_id not in children_of.get(parent, []):
            issues.append(f"semantic node {node_id}: not listed in parent {parent} children")
    return issues


def _check_semantic_relations(semantic: dict[str, Any], node_ids: set[str]) -> list[str]:
    issues: list[str] = []
    for relation in semantic.get("relations", []):
        rel_id = relation.get("id")
        issues.extend(
            _unknown_ref(
                relation.get("source"),
                node_ids,
                f"semantic relation {rel_id}: unknown source {relation.get('source')}",
            )
        )
        issues.extend(
            _unknown_ref(
                relation.get("target"),
                node_ids,
                f"semantic relation {rel_id}: unknown target {relation.get('target')}",
            )
        )
    return issues


def validate_bundle_references(bundle: dict[str, Any]) -> list[str]:
    """Validate ID references across a DocumentBundle-shaped dict.

    ``bundle`` maps layer names to documents: ``physical``, ``layout``,
    ``semantic``, ``mappings``, and optionally ``evidence``.
    """
    issues: list[str] = []

    physical = bundle.get("physical", {})
    layout = bundle.get("layout", {})
    semantic = bundle.get("semantic", {})
    mappings = bundle.get("mappings", {})

    page_ids_list = _collect_ids(physical, "pages")
    object_ids_list = _collect_ids(physical, "objects")
    region_ids_list = _collect_ids(layout, "regions")
    group_ids_list = _collect_ids(layout, "groups")
    node_ids_list = _collect_ids(semantic, "nodes")
    relation_ids_list = _collect_ids(semantic, "relations")
    plb_ids = _collect_ids(mappings, "physicalLayoutBindings")
    anchor_ids_list = _collect_ids(mappings, "sourceAnchors")
    ssb_ids = _collect_ids(mappings, "sourceSemanticBindings")

    issues.extend(_duplicate_issues(page_ids_list, "physical pages"))
    issues.extend(_duplicate_issues(object_ids_list, "physical objects"))
    issues.extend(_duplicate_issues(region_ids_list, "layout regions"))
    issues.extend(_duplicate_issues(group_ids_list, "layout groups"))
    issues.extend(_duplicate_issues(node_ids_list, "semantic nodes"))
    issues.extend(_duplicate_issues(relation_ids_list, "semantic relations"))
    issues.extend(_duplicate_issues(plb_ids, "physical-layout bindings"))
    issues.extend(_duplicate_issues(anchor_ids_list, "source anchors"))
    issues.extend(_duplicate_issues(ssb_ids, "source-semantic bindings"))

    page_ids = set(page_ids_list)
    object_ids = set(object_ids_list)
    region_ids = set(region_ids_list)
    node_ids = set(node_ids_list)
    anchor_ids = set(anchor_ids_list)

    issues.extend(_check_layout_references(layout, page_ids, object_ids))
    issues.extend(_check_semantic_tree(semantic, node_ids))
    issues.extend(_check_semantic_relations(semantic, node_ids))

    for binding in mappings.get("physicalLayoutBindings", []):
        region_ref = binding.get("layoutRegionId")
        if region_ref not in region_ids:
            binding_id = binding.get("id")
            issues.append(f"physical-layout binding {binding_id}: unknown region {region_ref}")
        issues.extend(
            f"physical-layout binding {binding.get('id')}: unknown physical object {obj_id}"
            for obj_id in binding.get("physicalObjectIds", [])
            if obj_id not in object_ids
        )

    for anchor in mappings.get("sourceAnchors", []):
        for fragment in anchor.get("fragments", []):
            region_ref = fragment.get("layoutRegionId")
            if region_ref is not None and region_ref not in region_ids:
                issues.append(f"source anchor {anchor.get('id')}: unknown region {region_ref}")

    for binding in mappings.get("sourceSemanticBindings", []):
        node_ref = binding.get("semanticNodeId")
        if node_ref not in node_ids:
            binding_id = binding.get("id")
            issues.append(f"source-semantic binding {binding_id}: unknown node {node_ref}")
        issues.extend(
            f"source-semantic binding {binding.get('id')}: unknown anchor {anchor_id}"
            for anchor_id in binding.get("sourceAnchorIds", [])
            if anchor_id not in anchor_ids
        )

    return issues
