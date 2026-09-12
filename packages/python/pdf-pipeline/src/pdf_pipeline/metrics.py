"""Layout recovery benchmark metrics (Roadmap M3 Validation, §6 Benchmark Policy).

All metrics compare a recovered LayoutDocument against a hand-derived
ground truth for the same fixture:

- Region Recall / Region Precision: ground-truth reading-order text
  snippets matched to regions by token-prefix matching, so the truth
  stays maintainable as plain snippets instead of coordinates.
- Pairwise ordering accuracy: fraction of matched region pairs whose
  relative order along the primary flow matches the truth sequence.
- Sequence accuracy: the matched snippets appear along the primary flow
  in exactly the truth order.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, cast

from document_model.generated import schema_models as generated

_TOKEN = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")


def _tokens(text: str) -> list[str]:
    """Lowercase alphanumeric tokens; punctuation and hyphenation dropped."""
    lowered = text.lower()
    return "".join(ch if ch in _TOKEN else " " for ch in lowered).split()


@dataclass(frozen=True)
class OrderMetrics:
    """Reading-order metrics for one fixture."""

    region_recall: float
    region_precision: float
    pairwise_ordering_accuracy: float
    sequence_accuracy: bool
    matched_regions: int
    truth_regions: int
    recovered_regions: int


def region_matches(
    truth_snippets: list[str],
    region_texts: dict[str, str],
) -> tuple[list[int], list[str]]:
    """Greedy matching of truth snippets to regions by token prefix.

    Matching happens in token space (punctuation and hyphenation
    stripped): a snippet matches the first unused region whose token
    sequence contains the snippet's leading tokens. Returns
    (truth_indices_matched, matched_region_ids), aligned to each other.
    """
    region_token_texts = {
        region_id: " ".join(_tokens(text)) for region_id, text in region_texts.items()
    }
    matched_truth: list[int] = []
    matched_regions: list[str] = []
    used: set[str] = set()
    for truth_index, snippet in enumerate(truth_snippets):
        tokens = _tokens(snippet)
        if not tokens:
            continue
        probe = " ".join(tokens[:6])
        for region_id, text in region_token_texts.items():
            if region_id in used or not text:
                continue
            if probe in text:
                matched_truth.append(truth_index)
                matched_regions.append(region_id)
                used.add(region_id)
                break
    return matched_truth, matched_regions


def order_metrics(
    truth_snippets: list[str],
    primary_flow: list[str],
    region_texts: dict[str, str],
) -> OrderMetrics:
    """Compute the M3 reading-order metrics for one document.

    ``region_texts`` maps layout region id -> recovered text. Recall still
    counts snippets that landed in excluded regions (footers, footnotes)
    against the score. Precision is computed only over non-empty primary-flow
    text regions: snippet-level ground truth cannot support region-level
    precision against every recovered fragment.
    """
    matched_truth, matched_regions = region_matches(truth_snippets, region_texts)

    flow_position = {region_id: index for index, region_id in enumerate(primary_flow)}
    positions = [
        flow_position[region_id] for region_id in matched_regions if region_id in flow_position
    ]
    flow_text_ids = [
        region_id for region_id in primary_flow if region_texts.get(region_id, "").strip()
    ]

    pairs_total = 0
    pairs_correct = 0
    for i in range(len(positions)):
        for j in range(i + 1, len(positions)):
            pairs_total += 1
            if positions[i] < positions[j]:
                pairs_correct += 1
    pairwise = pairs_correct / pairs_total if pairs_total else 1.0
    matched_in_flow = sum(1 for region_id in matched_regions if region_id in flow_position)

    return OrderMetrics(
        region_recall=len(matched_truth) / len(truth_snippets) if truth_snippets else 1.0,
        region_precision=matched_in_flow / len(flow_text_ids) if flow_text_ids else 1.0,
        pairwise_ordering_accuracy=round(pairwise, 4),
        sequence_accuracy=positions == sorted(positions),
        matched_regions=len(matched_truth),
        truth_regions=len(truth_snippets),
        recovered_regions=len(region_texts),
    )


# Semantic node kinds whose SourceAnchor/RenderAnchor coverage counts
# toward mapping coverage (containers are excluded).
_ANCHORED_KINDS = frozenset(
    {"PARAGRAPH", "HEADING", "FIGURE", "TABLE", "EQUATION", "FOOTNOTE", "BIBLIOGRAPHY_ENTRY"}
)


def physical_text_coverage(
    physical: generated.PhysicalDocument,
    region_texts: dict[str, str],
) -> float:
    """Share of extracted body characters assigned to layout regions."""
    total = sum(len(span.text) for span in physical.objects if isinstance(span, generated.TextSpan))
    if total <= 0:
        return 1.0
    covered = sum(len(text) for text in region_texts.values())
    return round(min(covered / total, 1.0), 4)


def citation_resolution_rate(semantic: generated.SemanticDocument) -> float:
    """Resolved share of CITATION marks (unresolved ones surface as issues)."""
    marks = sum(
        1
        for node in semantic.nodes
        if isinstance(node.content, generated.RichText)
        for mark in node.content.marks
        if mark.type == "CITATION"
    )
    if marks == 0:
        return 1.0
    unresolved = sum(
        1
        for issue in (semantic.issues.issues if semantic.issues else [])
        if issue.category == "CITATION_RESOLUTION"
    )
    return round(max(1.0 - unresolved / marks, 0.0), 4)


def source_mapping_coverage(semantic: generated.SemanticDocument) -> float:
    """Share of content nodes anchored to source layout regions."""
    content = [n for n in semantic.nodes if n.kind in _ANCHORED_KINDS]
    if not content:
        return 1.0
    anchored = sum(1 for n in content if n.attributes.get("layoutRegionIds"))
    return round(anchored / len(content), 4)


def render_mapping_coverage(
    semantic: generated.SemanticDocument,
    mapping: generated.MappingBundle | None,
) -> float:
    """Share of content nodes with at least one rendered fragment."""
    content = [n for n in semantic.nodes if n.kind in _ANCHORED_KINDS]
    if not content:
        return 1.0
    if mapping is None:
        return 0.0
    rendered = {str(anchor.semanticNodeId) for anchor in getattr(mapping, "renderAnchors", [])}
    covered = sum(1 for n in content if n.id in rendered)
    return round(covered / len(content), 4)


def table_structure_coverage(semantic: generated.SemanticDocument) -> float:
    """Share of TABLE nodes carrying explicit multi-column cell structure."""
    tables = [n for n in semantic.nodes if n.kind == "TABLE"]
    if not tables:
        return 1.0
    structured = sum(
        1 for n in tables if isinstance(n.content, generated.TableContent) and n.content.columns > 1
    )
    return round(structured / len(tables), 4)


def issue_counts(semantic: generated.SemanticDocument) -> dict[str, int]:
    """Issue counts by category for the report's observability section."""
    counts: dict[str, int] = {}
    for issue in semantic.issues.issues if semantic.issues else []:
        counts[issue.category] = counts.get(issue.category, 0) + 1
    return counts


def issue_severity_counts(semantic: generated.SemanticDocument) -> dict[str, int]:
    """Issue counts by severity (ERROR/FATAL are the blocking gate)."""
    counts: dict[str, int] = {}
    for issue in semantic.issues.issues if semantic.issues else []:
        counts[issue.severity] = counts.get(issue.severity, 0) + 1
    return counts


def quality_report(
    *,
    physical: generated.PhysicalDocument,
    layout: generated.LayoutDocument,
    semantic: generated.SemanticDocument,
    region_texts: dict[str, str],
    truth: dict[str, Any] | None = None,
    mapping: generated.MappingBundle | None = None,
) -> dict[str, object]:
    """Build the Phase 7.6 quality report for one document.

    Combines the M3 order metrics (when hand truth is available), text
    coverage, mapping coverage, citation resolution, and table structure
    into one JSON-able artifact. Metrics that need unavailable inputs are
    reported as null rather than invented.
    """
    truth_data: dict[str, Any] = truth if truth is not None else {}
    raw_snippets: Any = truth_data.get("readingOrder")
    snippet_list = cast("list[Any]", raw_snippets) if isinstance(raw_snippets, list) else []
    snippets = [str(snippet) for snippet in snippet_list]
    order = order_metrics(snippets, list(layout.primaryFlow), region_texts)
    semantic_truth: dict[str, Any] = truth_data.get("semantic") or {}
    # Paragraph/section *accuracy* needs region-level annotated truth that
    # this corpus does not have. Report the checks we can actually run
    # under their real names; the accuracy slots stay null.
    return {
        "physicalTextCoverage": physical_text_coverage(physical, region_texts),
        "regionRecall": round(order.region_recall, 4),
        "regionPrecision": round(order.region_precision, 4),
        "pairwiseOrderingAccuracy": order.pairwise_ordering_accuracy,
        "sequenceAccuracy": order.sequence_accuracy,
        "paragraphRecoveryAccuracy": None,
        "sectionHierarchyAccuracy": None,
        "semanticExpectationCoverage": None
        if not semantic_truth
        else round(_expectation_score(semantic, semantic_truth), 4),
        "tableStructureCoverage": table_structure_coverage(semantic),
        "citationResolutionRate": citation_resolution_rate(semantic),
        "sourceMappingCoverage": source_mapping_coverage(semantic),
        "renderMappingCoverage": render_mapping_coverage(semantic, mapping),
        "issues": {
            "byCategory": issue_counts(semantic),
            "bySeverity": issue_severity_counts(semantic),
        },
    }


def _expectation_score(
    semantic: generated.SemanticDocument,
    semantic_truth: dict[str, Any],
) -> float:
    """Share of truth expectations satisfied (kinds present, min counts)."""
    checks = 0
    passed = 0
    kinds = {node.kind for node in semantic.nodes}
    raw_kinds = semantic_truth.get("kinds")
    kind_list = cast("list[object]", raw_kinds) if isinstance(raw_kinds, list) else []
    expected_kinds = [str(kind) for kind in kind_list]
    for kind in expected_kinds:
        checks += 1
        if kind in kinds:
            passed += 1
    counts = Counter(node.kind for node in semantic.nodes)
    raw_min_counts: Any = semantic_truth.get("minCounts")
    min_counts: dict[str, Any] = (
        cast("dict[str, Any]", raw_min_counts) if isinstance(raw_min_counts, dict) else {}
    )
    for raw_kind, minimum in min_counts.items():
        kind = str(raw_kind)
        checks += 1
        if counts.get(kind, 0) >= int(minimum):
            passed += 1
    return passed / checks if checks else 1.0


__all__ = [
    "OrderMetrics",
    "citation_resolution_rate",
    "issue_counts",
    "issue_severity_counts",
    "order_metrics",
    "physical_text_coverage",
    "quality_report",
    "region_matches",
    "render_mapping_coverage",
    "source_mapping_coverage",
    "table_structure_coverage",
]
