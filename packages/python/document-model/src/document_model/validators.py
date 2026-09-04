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


def _collect_ids(document: dict[str, Any], key: str) -> set[str]:
    return {item["id"] for item in document.get(key, []) if "id" in item}


def _check_layout_references(
    layout: dict[str, Any], page_ids: set[str], object_ids: set[str]
) -> list[str]:
    issues: list[str] = []
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

    page_ids = {page["id"] for page in physical.get("pages", [])}
    object_ids = {obj["id"] for obj in physical.get("objects", [])}

    region_ids = {region["id"] for region in layout.get("regions", [])}
    node_ids = {node["id"] for node in semantic.get("nodes", [])}

    # layout region references must resolve to pages and physical objects
    issues.extend(_check_layout_references(layout, page_ids, object_ids))

    # semantic tree references must resolve
    for node in semantic.get("nodes", []):
        parent = node.get("parentId")
        if parent is not None and parent not in node_ids:
            issues.append(f"semantic node {node.get('id')}: unknown parent {parent}")
        issues.extend(
            f"semantic node {node.get('id')}: unknown child {child}"
            for child in node.get("children", [])
            if child not in node_ids
        )
        if semantic.get("rootId") is None:
            issues.append("semantic document: missing rootId")

    # mapping references must resolve into their layers
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

    anchor_ids = _collect_ids(mappings, "sourceAnchors")
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
