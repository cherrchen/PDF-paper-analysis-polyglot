"""Phase 4.9 semantic validation: post-recovery integrity issues.

Recovery is allowed to be wrong; it must not be silently wrong. This
module audits a recovered SemanticDocument (against its layout) and
returns canonical Issues: orphan nodes, broken section trees, unbound
content, dangling references, caption-less blocks, and coverage holes.
The checks are pure and deterministic — same inputs, same issue list.
"""

from __future__ import annotations

from itertools import pairwise
from typing import TYPE_CHECKING, cast

from document_model.generated import schema_models as generated

from pdf_pipeline.ids import stable_uuid

if TYPE_CHECKING:
    from collections.abc import Mapping

SEMANTIC_PRODUCER = "pdf-pipeline.semantic-validator"

# Node kinds that must be bound to at least one layout region.
_BOUND_KINDS = frozenset(
    {
        "PARAGRAPH",
        "HEADING",
        "FIGURE",
        "FIGURE_CAPTION",
        "TABLE",
        "TABLE_CAPTION",
        "EQUATION",
        "FOOTNOTE",
        "BIBLIOGRAPHY_ENTRY",
    }
)
# Marks whose resolved targets must carry the right kind.
_MARK_TARGET_KINDS: dict[str, set[str]] = {
    "CITATION": {"BIBLIOGRAPHY_ENTRY"},
    "FOOTNOTE_REFERENCE": {"FOOTNOTE"},
}
# Relations whose target must carry the right kind.
_RELATION_TARGET_KINDS: dict[str, set[str]] = {
    "CAPTION_OF": {"FIGURE", "TABLE"},
    "CITES": {"BIBLIOGRAPHY_ENTRY"},
    "FOOTNOTE_OF": {"PARAGRAPH", "UNKNOWN"},
}

COVERAGE_MIN_RATIO = 0.95


def validate_semantic_recovery(
    semantic: generated.SemanticDocument,
    layout: generated.LayoutDocument,
    region_texts: Mapping[str, str],
) -> list[generated.Issue]:
    """Audit one recovered SemanticDocument; return issues (possibly empty)."""
    nodes_by_id = {node.id: node for node in semantic.nodes}
    issues: list[generated.Issue] = []
    issues.extend(_tree_issues(semantic, nodes_by_id))
    issues.extend(_binding_issues(semantic, layout))
    issues.extend(_reference_issues(semantic, nodes_by_id))
    issues.extend(_caption_issues(semantic))
    issues.extend(_coverage_issues(semantic, layout, region_texts))
    return issues


def _tree_issues(
    semantic: generated.SemanticDocument,
    nodes_by_id: Mapping[str, generated.SemanticNode],
) -> list[generated.Issue]:
    issues: list[generated.Issue] = []
    reachable: set[str] = set()
    stack = [semantic.rootId]
    while stack:
        node_id = stack.pop()
        if node_id in reachable:
            continue
        reachable.add(node_id)
        node = nodes_by_id.get(node_id)
        if node is not None:
            stack.extend(node.children)

    issues.extend(
        _issue(
            semantic.id,
            "SECTION_STRUCTURE",
            "ERROR",
            f"orphan node {node.id} is unreachable from the document root",
            [node.id],
        )
        for node in semantic.nodes
        if node.id != semantic.rootId and node.id not in reachable
    )

    levels = _headings_in_tree_order(semantic, nodes_by_id)
    for (level, node_id), (next_level, next_id) in pairwise(levels):
        if next_level > level + 1:
            issues.append(
                _issue(
                    semantic.id,
                    "SECTION_STRUCTURE",
                    "WARNING",
                    f"heading level jumps from {level} to {next_level} ({node_id} -> {next_id})",
                    [node_id, next_id],
                )
            )
    return issues


def _headings_in_tree_order(
    semantic: generated.SemanticDocument,
    nodes_by_id: Mapping[str, generated.SemanticNode],
) -> list[tuple[int, str]]:
    """HEADING levels in document-tree order, including nested SECTION trees."""
    headings: list[tuple[int, str]] = []

    def walk(node_id: str) -> None:
        node = nodes_by_id.get(node_id)
        if node is None:
            return
        if node.kind == "HEADING":
            level = _heading_level(node)
            if level is not None:
                headings.append((level, node.id))
        for child_id in node.children:
            walk(child_id)

    walk(semantic.rootId)
    return headings


def _heading_level(node: generated.SemanticNode) -> int | None:
    level = node.attributes.get("level")
    return level if isinstance(level, int) else None


def _binding_issues(
    semantic: generated.SemanticDocument,
    layout: generated.LayoutDocument,
) -> list[generated.Issue]:
    issues: list[generated.Issue] = []
    region_ids = {region.id for region in layout.regions}
    for node in semantic.nodes:
        if node.kind not in _BOUND_KINDS:
            continue
        raw = node.attributes.get("layoutRegionIds")
        bound = [item for item in cast("list[object]", raw) if isinstance(item, str)] if raw else []
        if not bound:
            issues.append(
                _issue(
                    semantic.id,
                    "SOURCE_MAPPING",
                    "ERROR",
                    f"{node.kind} node {node.id} has no source layout regions",
                    [node.id],
                )
            )
            continue
        unknown = [region_id for region_id in bound if region_id not in region_ids]
        if unknown:
            issues.append(
                _issue(
                    semantic.id,
                    "SOURCE_MAPPING",
                    "ERROR",
                    f"node {node.id} references unknown layout regions {unknown}",
                    [node.id, *unknown],
                )
            )
    return issues


def _reference_issues(
    semantic: generated.SemanticDocument,
    nodes_by_id: Mapping[str, generated.SemanticNode],
) -> list[generated.Issue]:
    issues: list[generated.Issue] = []
    for node in semantic.nodes:
        content = node.content
        marks = content.marks if isinstance(content, generated.RichText) else []
        for mark in marks:
            allowed = _MARK_TARGET_KINDS.get(mark.type)
            if allowed is None or mark.targetNodeId is None:
                continue
            target = nodes_by_id.get(mark.targetNodeId)
            if target is None or target.kind not in allowed:
                category: generated.IssueCategory = (
                    "CITATION_RESOLUTION" if mark.type == "CITATION" else "SOURCE_MAPPING"
                )
                issues.append(
                    _issue(
                        semantic.id,
                        category,
                        "WARNING",
                        f"{mark.type} mark in node {node.id} targets "
                        f"{mark.targetNodeId} of unexpected kind",
                        [node.id, mark.targetNodeId],
                    )
                )
    for relation in semantic.relations:
        allowed = _RELATION_TARGET_KINDS.get(relation.type)
        if allowed is None:
            continue
        target = nodes_by_id.get(relation.target)
        if target is None or target.kind not in allowed:
            category = "CITATION_RESOLUTION" if relation.type == "CITES" else "SOURCE_MAPPING"
            issues.append(
                _issue(
                    semantic.id,
                    category,
                    "WARNING",
                    f"relation {relation.type} {relation.source} -> {relation.target} "
                    "has an unexpected target kind",
                    [relation.source, relation.target],
                )
            )
    return issues


def _caption_issues(semantic: generated.SemanticDocument) -> list[generated.Issue]:
    caption_targets = {
        relation.source for relation in semantic.relations if relation.type == "CAPTION_OF"
    }
    issues: list[generated.Issue] = []
    for node in semantic.nodes:
        if node.kind not in {"FIGURE_CAPTION", "TABLE_CAPTION"}:
            continue
        if node.id in caption_targets:
            continue
        category: generated.IssueCategory = (
            "TABLE_RECOVERY" if node.kind == "TABLE_CAPTION" else "FIGURE_RECOVERY"
        )
        issues.append(
            _issue(
                semantic.id,
                category,
                "WARNING",
                f"caption node {node.id} has no CAPTION_OF relation",
                [node.id],
            )
        )
    return issues


def _coverage_issues(
    semantic: generated.SemanticDocument,
    layout: generated.LayoutDocument,
    region_texts: Mapping[str, str],
) -> list[generated.Issue]:
    """Every content region must belong to exactly one node."""
    covered: dict[str, int] = {}
    for node in semantic.nodes:
        raw = node.attributes.get("layoutRegionIds")
        if isinstance(raw, list):
            for region_id in cast("list[object]", raw):
                if isinstance(region_id, str):
                    covered[region_id] = covered.get(region_id, 0) + 1

    primary = set(layout.primaryFlow)
    required = [
        region.id
        for region in layout.regions
        if region.id in primary
        and region.kind in {"TEXT", "TABLE", "FORMULA"}
        and region_texts.get(region.id, "").strip()
    ]
    missing = [region_id for region_id in required if covered.get(region_id, 0) == 0]
    double = [region_id for region_id in required if covered.get(region_id, 0) > 1]
    issues: list[generated.Issue] = []
    if missing:
        ratio = (len(required) - len(missing)) / len(required) if required else 1.0
        severity: generated.IssueSeverity = "ERROR" if ratio < COVERAGE_MIN_RATIO else "WARNING"
        issues.append(
            _issue(
                semantic.id,
                "SOURCE_MAPPING",
                severity,
                f"{len(missing)} primary-flow regions are not covered by any semantic node: "
                f"{missing}",
                missing,
            )
        )
    if double:
        issues.append(
            _issue(
                semantic.id,
                "SOURCE_MAPPING",
                "ERROR",
                f"regions covered by multiple semantic nodes: {double}",
                double,
            )
        )
    return issues


def _issue(
    semantic_id: str,
    category: generated.IssueCategory,
    severity: generated.IssueSeverity,
    message: str,
    affected_ids: list[str],
) -> generated.Issue:
    return generated.Issue(
        id=stable_uuid(semantic_id, "issue", category, severity, message),
        category=category,
        severity=severity,
        producer=SEMANTIC_PRODUCER,
        message=message,
        affectedIds=affected_ids,
        recoverable=True,
    )
