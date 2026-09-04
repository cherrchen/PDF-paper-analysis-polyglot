"""Cross-layer validators for the canonical document contracts.

These checks encode the permanent architecture boundaries:

- Semantic layer must never carry layout geometry (page, bbox, column).
- Layout layer must never carry paper semantics.
- ID references inside a bundle must resolve.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, cast

type JsonValue = dict[str, JsonValue] | list[JsonValue] | str | int | float | bool | None

_GEOMETRY_KEYS = {"page", "bbox", "column", "pagebreak", "pagesize", "font", "fontsize"}
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


def _geometry_paths(value: JsonValue, path: str) -> list[str]:
    """Find forbidden geometry keys recursively inside an open attribute bag."""
    issues: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if _is_geometry_key(key):
                issues.append(child_path)
            issues.extend(_geometry_paths(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            issues.extend(_geometry_paths(child, f"{path}[{index}]"))
    return issues


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
            f"semantic node {node_id}: geometry attribute {path!r} not allowed"
            for path in _geometry_paths(node.get("attributes", {}), "attributes")
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


def _reference_issues(refs: list[str], known: set[str], message: str) -> list[str]:
    return [message.format(ref=ref) for ref in refs if ref not in known]


def _walk_objects(value: JsonValue) -> list[dict[str, JsonValue]]:
    """Collect dictionaries recursively from a JSON-shaped value."""
    objects: list[dict[str, JsonValue]] = []
    if isinstance(value, dict):
        objects.append(value)
        for child in value.values():
            objects.extend(_walk_objects(child))
    elif isinstance(value, list):
        for child in value:
            objects.extend(_walk_objects(child))
    return objects


def _check_local_stores(document: dict[str, Any], label: str) -> list[str]:
    """Validate references owned by per-document provenance and issue stores."""
    issues: list[str] = []
    provenance_value = document.get("provenance")
    provenance = (
        cast("dict[str, Any]", provenance_value) if isinstance(provenance_value, dict) else {}
    )
    provenance_ids = _collect_ids(provenance, "records")
    issues.extend(_duplicate_issues(provenance_ids, f"{label} provenance records"))
    known_provenance = set(provenance_ids)
    for item in _walk_objects(cast("dict[str, JsonValue]", document)):
        refs = item.get("provenanceIds")
        if isinstance(refs, list):
            issues.extend(
                _reference_issues(
                    cast("list[str]", refs),
                    known_provenance,
                    f"{label}: unknown provenance {{ref}}",
                )
            )

    issue_store_value = document.get("issues")
    issue_store = (
        cast("dict[str, Any]", issue_store_value) if isinstance(issue_store_value, dict) else {}
    )
    issue_ids = _collect_ids(issue_store, "issues")
    issues.extend(_duplicate_issues(issue_ids, f"{label} issues"))
    return issues


def _check_physical_references(
    physical: dict[str, Any], page_ids: set[str], object_ids: set[str]
) -> list[str]:
    issues: list[str] = []
    objects_by_id = {item["id"]: item for item in physical.get("objects", []) if "id" in item}
    for page in physical.get("pages", []):
        page_id = page.get("id")
        for object_id in page.get("objectIds", []):
            if object_id not in object_ids:
                issues.append(f"physical page {page_id}: unknown object {object_id}")
            elif objects_by_id[object_id].get("pageId") != page_id:
                issues.append(
                    f"physical page {page_id}: object {object_id} belongs to "
                    f"page {objects_by_id[object_id].get('pageId')}"
                )
    pages_by_object: dict[str, set[str]] = {}
    for page in physical.get("pages", []):
        for object_id in page.get("objectIds", []):
            pages_by_object.setdefault(object_id, set()).add(page.get("id"))
    for item in physical.get("objects", []):
        object_id = item.get("id")
        page_id = item.get("pageId")
        if page_id not in page_ids:
            issues.append(f"physical object {object_id}: unknown pageId {page_id}")
        elif page_id not in pages_by_object.get(object_id, set()):
            issues.append(f"physical object {object_id}: not listed by page {page_id}")
    return issues


@dataclass(frozen=True)
class _LayoutIndex:
    pages: set[str]
    objects: set[str]
    regions: set[str]
    bands: set[str]
    columns: set[str]
    evidence: set[str] | None
    regions_by_id: dict[str, dict[str, Any]]
    bands_by_id: dict[str, dict[str, Any]]
    layout_pages_by_id: dict[str, dict[str, Any]]


def _check_layout_pages(layout: dict[str, Any], index: _LayoutIndex) -> list[str]:
    issues: list[str] = []
    for page in layout.get("pages", []):
        page_id = page.get("pageId")
        if page_id not in index.pages:
            issues.append(f"layout page: unknown pageId {page_id}")
        for region_id in page.get("regionIds", []):
            if region_id not in index.regions:
                issues.append(f"layout page {page_id}: unknown region {region_id}")
            elif index.regions_by_id[region_id].get("pageId") != page_id:
                issues.append(
                    f"layout page {page_id}: region {region_id} belongs to "
                    f"page {index.regions_by_id[region_id].get('pageId')}"
                )
        for band_id in page.get("bandIds", []):
            if band_id not in index.bands:
                issues.append(f"layout page {page_id}: unknown band {band_id}")
            elif index.bands_by_id[band_id].get("pageId") != page_id:
                issues.append(
                    f"layout page {page_id}: band {band_id} belongs to "
                    f"page {index.bands_by_id[band_id].get('pageId')}"
                )
    return issues


def _check_layout_regions(layout: dict[str, Any], index: _LayoutIndex) -> list[str]:
    issues: list[str] = []
    for region in layout.get("regions", []):
        region_id = region.get("id")
        page_id = region.get("pageId")
        if page_id not in index.pages:
            issues.append(f"layout region {region_id}: unknown pageId {page_id}")
        elif region_id not in index.layout_pages_by_id.get(page_id, {}).get("regionIds", []):
            issues.append(f"layout region {region_id}: not listed by layout page {page_id}")
        issues.extend(
            f"layout region {region_id}: unknown physical object {object_id}"
            for object_id in region.get("physicalObjectIds", [])
            if object_id not in index.objects
        )
        issues.extend(
            f"layout region {region_id}: unknown child {child}"
            for child in region.get("childIds", [])
            if child not in index.regions
        )
        if index.evidence is not None:
            for label in region.get("labels", []):
                issues.extend(
                    f"layout region {region_id}: unknown evidence {evidence_id}"
                    for evidence_id in label.get("evidenceIds", [])
                    if evidence_id not in index.evidence
                )
    return issues


def _check_layout_bands_and_columns(layout: dict[str, Any], index: _LayoutIndex) -> list[str]:
    issues: list[str] = []
    for band in layout.get("bands", []):
        band_id = band.get("id")
        page_id = band.get("pageId")
        if page_id not in index.pages:
            issues.append(f"layout band {band_id}: unknown pageId {page_id}")
        elif band_id not in index.layout_pages_by_id.get(page_id, {}).get("bandIds", []):
            issues.append(f"layout band {band_id}: not listed by layout page {page_id}")
        issues.extend(
            f"layout band {band_id}: unknown column {column_id}"
            for column_id in band.get("columnIds", [])
            if column_id not in index.columns
        )

    for column in layout.get("columns", []):
        column_id = column.get("id")
        page_id = column.get("pageId")
        band_id = column.get("bandId")
        if page_id not in index.pages:
            issues.append(f"layout column {column_id}: unknown pageId {page_id}")
        if band_id not in index.bands:
            issues.append(f"layout column {column_id}: unknown bandId {band_id}")
        elif index.bands_by_id[band_id].get("pageId") != page_id:
            issues.append(
                f"layout column {column_id}: band {band_id} belongs to "
                f"page {index.bands_by_id[band_id].get('pageId')}"
            )
        elif column_id not in index.bands_by_id[band_id].get("columnIds", []):
            issues.append(f"layout column {column_id}: not listed by band {band_id}")
        issues.extend(
            f"layout column {column_id}: unknown region {region_id}"
            for region_id in column.get("regionIds", [])
            if region_id not in index.regions
        )
        issues.extend(
            f"layout column {column_id}: region {region_id} belongs to "
            f"page {index.regions_by_id[region_id].get('pageId')}"
            for region_id in column.get("regionIds", [])
            if region_id in index.regions
            and index.regions_by_id[region_id].get("pageId") != page_id
        )
    return issues


def _check_layout_groups(
    layout: dict[str, Any],
    page_ids: set[str],
    region_ids: set[str],
    regions_by_id: dict[str, dict[str, Any]],
) -> list[str]:
    issues: list[str] = []
    for group in layout.get("groups", []):
        issues.extend(
            f"layout group {group.get('id')}: unknown member {member}"
            for member in group.get("memberIds", [])
            if member not in region_ids
        )
        page_id = group.get("pageId")
        if page_id is not None and page_id not in page_ids:
            issues.append(f"layout group {group.get('id')}: unknown pageId {page_id}")
        elif page_id is not None:
            issues.extend(
                f"layout group {group.get('id')}: member {member} belongs to "
                f"page {regions_by_id[member].get('pageId')}"
                for member in group.get("memberIds", [])
                if member in region_ids and regions_by_id[member].get("pageId") != page_id
            )
    return issues


def _check_layout_reading_flow(layout: dict[str, Any], region_ids: set[str]) -> list[str]:
    issues: list[str] = []
    reading_flow = layout.get("readingFlow", {})
    flow_node_ids = set(reading_flow.get("nodes", []))
    issues.extend(
        f"layout reading flow: unknown node {node_id}"
        for node_id in reading_flow.get("nodes", [])
        if node_id not in region_ids
    )
    for edge in reading_flow.get("edges", []):
        for endpoint in ("source", "target"):
            ref = edge.get(endpoint)
            if ref not in region_ids:
                issues.append(f"layout reading edge: unknown {endpoint} {ref}")
            elif ref not in flow_node_ids:
                issues.append(f"layout reading edge: {endpoint} {ref} is not a graph node")
    issues.extend(
        f"layout primary flow: unknown region {region_id}"
        for region_id in layout.get("primaryFlow", [])
        if region_id not in region_ids
    )
    issues.extend(
        f"layout primary flow: region {region_id} is not a reading-flow node"
        for region_id in layout.get("primaryFlow", [])
        if region_id in region_ids and region_id not in flow_node_ids
    )
    return issues


def _check_layout_references(
    layout: dict[str, Any],
    page_ids: set[str],
    object_ids: set[str],
    evidence_ids: set[str] | None,
) -> list[str]:
    regions_by_id = {region["id"]: region for region in layout.get("regions", []) if "id" in region}
    bands_by_id = {band["id"]: band for band in layout.get("bands", []) if "id" in band}
    index = _LayoutIndex(
        pages=page_ids,
        objects=object_ids,
        regions=set(regions_by_id),
        bands=set(bands_by_id),
        columns={column["id"] for column in layout.get("columns", []) if "id" in column},
        evidence=evidence_ids,
        regions_by_id=regions_by_id,
        bands_by_id=bands_by_id,
        layout_pages_by_id={
            page["pageId"]: page for page in layout.get("pages", []) if "pageId" in page
        },
    )

    issues = _check_layout_pages(layout, index)
    issues.extend(_check_layout_regions(layout, index))
    issues.extend(_check_layout_bands_and_columns(layout, index))
    issues.extend(_check_layout_groups(layout, index.pages, index.regions, index.regions_by_id))
    issues.extend(_check_layout_reading_flow(layout, index.regions))
    return issues


def _check_evidence_references(
    evidence: dict[str, Any], page_ids: set[str], evidence_ids: set[str]
) -> list[str]:
    issues: list[str] = []
    for candidate in evidence.get("candidates", []):
        candidate_id = candidate.get("id")
        page_id = candidate.get("pageId")
        if page_id is not None and page_id not in page_ids:
            issues.append(f"evidence candidate {candidate_id}: unknown pageId {page_id}")
        parent_id = candidate.get("parentId")
        if parent_id is not None and parent_id not in evidence_ids:
            issues.append(f"evidence candidate {candidate_id}: unknown parentId {parent_id}")
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


def _check_inline_references(semantic: dict[str, Any], node_ids: set[str]) -> list[str]:
    issues: list[str] = []
    for node in semantic.get("nodes", []):
        content_value = node.get("content")
        content = cast("dict[str, Any]", content_value) if isinstance(content_value, dict) else {}
        marks_value = content.get("marks", [])
        marks = cast("list[Any]", marks_value) if isinstance(marks_value, list) else []
        for mark_value in marks:
            if not isinstance(mark_value, dict):
                continue
            mark = cast("dict[str, Any]", mark_value)
            target = mark.get("targetNodeId")
            if target is not None and target not in node_ids:
                issues.append(
                    f"semantic node {node.get('id')}: inline mark has unknown target {target}"
                )
    return issues


@dataclass(frozen=True)
class _BundleDocuments:
    physical: dict[str, Any]
    layout: dict[str, Any]
    semantic: dict[str, Any]
    mappings: dict[str, Any]
    evidence: dict[str, Any] | None
    translation: dict[str, Any] | None
    render: dict[str, Any] | None


@dataclass(frozen=True)
class _BundleIds:
    pages: set[str]
    objects: set[str]
    regions: set[str]
    nodes: set[str]
    anchors: set[str]
    evidence: set[str]


def _document(bundle: dict[str, Any], key: str) -> dict[str, Any]:
    value = bundle.get(key)
    return cast("dict[str, Any]", value) if isinstance(value, dict) else {}


def _bundle_documents(bundle: dict[str, Any]) -> _BundleDocuments:
    evidence_value = bundle.get("evidence")
    evidence = cast("dict[str, Any]", evidence_value) if isinstance(evidence_value, dict) else None
    translation_value = bundle.get("translation")
    translation = (
        cast("dict[str, Any]", translation_value) if isinstance(translation_value, dict) else None
    )
    render_value = bundle.get("render")
    render = cast("dict[str, Any]", render_value) if isinstance(render_value, dict) else None
    return _BundleDocuments(
        physical=_document(bundle, "physical"),
        layout=_document(bundle, "layout"),
        semantic=_document(bundle, "semantic"),
        mappings=_document(bundle, "mappings"),
        evidence=evidence,
        translation=translation,
        render=render,
    )


def _build_bundle_ids(documents: _BundleDocuments) -> tuple[_BundleIds, list[str]]:
    physical = documents.physical
    layout = documents.layout
    semantic = documents.semantic
    mappings = documents.mappings
    evidence = documents.evidence
    page_ids = _collect_ids(physical, "pages")
    object_ids = _collect_ids(physical, "objects")
    region_ids = _collect_ids(layout, "regions")
    node_ids = _collect_ids(semantic, "nodes")
    anchor_ids = _collect_ids(mappings, "sourceAnchors")
    evidence_ids = _collect_ids(evidence, "candidates") if evidence is not None else []
    definitions = (
        ("physical pages", page_ids),
        ("physical objects", object_ids),
        (
            "layout pages",
            [page["pageId"] for page in layout.get("pages", []) if "pageId" in page],
        ),
        ("layout regions", region_ids),
        ("layout groups", _collect_ids(layout, "groups")),
        ("layout bands", _collect_ids(layout, "bands")),
        ("layout columns", _collect_ids(layout, "columns")),
        ("semantic nodes", node_ids),
        ("semantic relations", _collect_ids(semantic, "relations")),
        ("physical-layout bindings", _collect_ids(mappings, "physicalLayoutBindings")),
        ("source anchors", anchor_ids),
        ("source-semantic bindings", _collect_ids(mappings, "sourceSemanticBindings")),
        ("render bindings", _collect_ids(mappings, "renderBindings")),
        ("evidence candidates", evidence_ids),
    )
    issues = [issue for label, ids in definitions for issue in _duplicate_issues(ids, label)]
    return (
        _BundleIds(
            pages=set(page_ids),
            objects=set(object_ids),
            regions=set(region_ids),
            nodes=set(node_ids),
            anchors=set(anchor_ids),
            evidence=set(evidence_ids),
        ),
        issues,
    )


def _check_cross_document_references(documents: _BundleDocuments) -> list[str]:
    issues: list[str] = []
    physical_id = documents.physical.get("id")
    layout_physical_id = documents.layout.get("physicalDocumentId")
    if physical_id is not None and layout_physical_id != physical_id:
        issues.append(
            f"layout document: physicalDocumentId {layout_physical_id} does not match {physical_id}"
        )
    layout_id = documents.layout.get("id")
    semantic_layout_id = documents.semantic.get("layoutDocumentId")
    if semantic_layout_id is not None and layout_id is not None and semantic_layout_id != layout_id:
        issues.append(
            f"semantic document: layoutDocumentId {semantic_layout_id} does not match {layout_id}"
        )
    semantic_id = documents.semantic.get("id")
    node_ids = set(_collect_ids(documents.semantic, "nodes"))
    if documents.translation is not None:
        translation_semantic_id = documents.translation.get("semanticDocumentId")
        if semantic_id is not None and translation_semantic_id != semantic_id:
            issues.append(
                "translation layer: semanticDocumentId "
                f"{translation_semantic_id} does not match {semantic_id}"
            )
        entry_node_ids = [
            node_id
            for entry in documents.translation.get("entries", [])
            if isinstance(node_id := entry.get("semanticNodeId"), str)
        ]
        issues.extend(_duplicate_issues(entry_node_ids, "translation entries"))
        issues.extend(
            f"translation entry: unknown semantic node {node_id}"
            for node_id in entry_node_ids
            if node_id not in node_ids
        )
    if documents.render is not None:
        render_semantic_id = documents.render.get("semanticDocumentId")
        if semantic_id is not None and render_semantic_id != semantic_id:
            issues.append(
                "render document: semanticDocumentId "
                f"{render_semantic_id} does not match {semantic_id}"
            )
        if documents.translation is not None:
            translation_id = documents.translation.get("id")
            render_translation_id = documents.render.get("translationLayerId")
            if render_translation_id is not None and render_translation_id != translation_id:
                issues.append(
                    "render document: translationLayerId "
                    f"{render_translation_id} does not match {translation_id}"
                )
        for block in documents.render.get("blocks", []):
            issues.extend(
                f"render block {block.get('id')}: unknown semantic node {node_id}"
                for node_id in block.get("semanticNodeIds", [])
                if node_id not in node_ids
            )
        render_id = documents.render.get("id")
        for binding in documents.mappings.get("renderBindings", []):
            binding_render_id = binding.get("renderDocumentId")
            if render_id is not None and binding_render_id != render_id:
                issues.append(
                    f"render binding {binding.get('id')}: renderDocumentId "
                    f"{binding_render_id} does not match {render_id}"
                )
    return issues


def _check_bundle_stores(documents: _BundleDocuments) -> list[str]:
    issues: list[str] = []
    for label, document in (
        ("physical document", documents.physical),
        ("layout document", documents.layout),
        ("semantic document", documents.semantic),
        ("mapping bundle", documents.mappings),
    ):
        issues.extend(_check_local_stores(document, label))
    if documents.evidence is not None:
        issues.extend(_check_local_stores(documents.evidence, "evidence bundle"))
    if documents.translation is not None:
        issues.extend(_check_local_stores(documents.translation, "translation layer"))
    if documents.render is not None:
        issues.extend(_check_local_stores(documents.render, "render document"))
    return issues


def _check_mapping_references(mappings: dict[str, Any], ids: _BundleIds) -> list[str]:
    issues: list[str] = []
    for binding in mappings.get("physicalLayoutBindings", []):
        region_ref = binding.get("layoutRegionId")
        if region_ref not in ids.regions:
            issues.append(
                f"physical-layout binding {binding.get('id')}: unknown region {region_ref}"
            )
        issues.extend(
            f"physical-layout binding {binding.get('id')}: unknown physical object {object_id}"
            for object_id in binding.get("physicalObjectIds", [])
            if object_id not in ids.objects
        )
    for anchor in mappings.get("sourceAnchors", []):
        for fragment in anchor.get("fragments", []):
            region_ref = fragment.get("layoutRegionId")
            if region_ref is not None and region_ref not in ids.regions:
                issues.append(f"source anchor {anchor.get('id')}: unknown region {region_ref}")
    for binding in mappings.get("sourceSemanticBindings", []):
        node_ref = binding.get("semanticNodeId")
        if node_ref not in ids.nodes:
            issues.append(f"source-semantic binding {binding.get('id')}: unknown node {node_ref}")
        issues.extend(
            f"source-semantic binding {binding.get('id')}: unknown anchor {anchor_id}"
            for anchor_id in binding.get("sourceAnchorIds", [])
            if anchor_id not in ids.anchors
        )
    return issues


def validate_bundle_references(bundle: dict[str, Any]) -> list[str]:
    """Validate ID references across a DocumentBundle-shaped dict.

    ``bundle`` maps layer names to documents: ``physical``, ``layout``,
    ``semantic``, ``mappings``, and optionally ``evidence``, ``translation``,
    and ``render``. References to resources and render anchors are external
    to these bundle documents and therefore cannot be resolved here.
    """
    documents = _bundle_documents(bundle)
    ids, issues = _build_bundle_ids(documents)
    issues.extend(_check_physical_references(documents.physical, ids.pages, ids.objects))
    issues.extend(
        _check_layout_references(
            documents.layout,
            ids.pages,
            ids.objects,
            ids.evidence if documents.evidence is not None else None,
        )
    )
    issues.extend(_check_semantic_tree(documents.semantic, ids.nodes))
    issues.extend(_check_semantic_relations(documents.semantic, ids.nodes))
    issues.extend(_check_inline_references(documents.semantic, ids.nodes))
    if documents.evidence is not None:
        issues.extend(_check_evidence_references(documents.evidence, ids.pages, ids.evidence))
    issues.extend(_check_cross_document_references(documents))
    issues.extend(_check_bundle_stores(documents))
    issues.extend(_check_mapping_references(documents.mappings, ids))
    return issues
