"""Layout recovery benchmark metrics (Roadmap M3 Validation, §6 Benchmark Policy).

All metrics compare a recovered LayoutDocument against a hand-derived
ground truth for the same fixture:

- Region Recall / Region Precision: when ``layout-truth.regions[]`` is
  present, IoU ≥ 0.5 plus LayoutLabel match. Otherwise reading-order
  snippets still drive order metrics (precision then cannot be region-level).
- Pairwise ordering accuracy: fraction of matched region pairs whose
  relative order along the primary flow matches the truth sequence.
- Sequence accuracy: the matched regions appear along the primary flow
  in exactly the truth order.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, cast

from document_model.generated import schema_models as generated

from pdf_pipeline.geometry import as_rect, iou

_TOKEN = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")

# Region-level annotated truth: a recovered region matches a labeled box
# when IoU is at least this and the LayoutLabel agrees.
REGION_IOU_THRESHOLD = 0.5
_FURNITURE_KINDS = frozenset({"HEADER", "FOOTER"})


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


@dataclass(frozen=True)
class TruthRegion:
    """One hand-labeled layout region; identity is geometry + label, not IDs."""

    page_index: int
    label: str
    rect: generated.Rect
    text_preview: str = ""


def parse_truth_regions(raw: object) -> list[TruthRegion]:
    """Parse ``layout-truth.regions[]``; skip malformed entries rather than crash."""
    if not isinstance(raw, list):
        return []
    regions: list[TruthRegion] = []
    for raw_item in cast("list[Any]", raw):
        if not isinstance(raw_item, dict):
            continue
        mapping = cast("dict[str, Any]", raw_item)
        geometry = mapping.get("geometry")
        if not isinstance(geometry, dict):
            continue
        geom = cast("dict[str, Any]", geometry)
        try:
            rect = generated.Rect(
                kind="rect",
                x=float(geom["x"]),
                y=float(geom["y"]),
                width=float(geom["width"]),
                height=float(geom["height"]),
            )
            regions.append(
                TruthRegion(
                    page_index=int(mapping.get("pageIndex") or 0),
                    label=str(mapping.get("label") or "UNKNOWN"),
                    rect=rect,
                    text_preview=str(mapping.get("textPreview") or ""),
                )
            )
        except (TypeError, ValueError, KeyError):
            continue
    return regions


def _dominant_label(region: generated.LayoutRegion) -> str:
    """LayoutLabel on the region; kind is a coarser visual class."""
    if region.labels:
        return str(region.labels[0].label)
    return str(region.kind)


def region_iou_matches(
    truth_regions: list[TruthRegion],
    layout: generated.LayoutDocument,
    *,
    threshold: float = REGION_IOU_THRESHOLD,
) -> tuple[list[int], list[str]]:
    """Greedy one-to-one matching of labeled boxes to recovered regions."""
    page_index = {page.pageId: index for index, page in enumerate(layout.pages)}
    unused = [region for region in layout.regions if region.kind not in _FURNITURE_KINDS]
    matched_truth: list[int] = []
    matched_ids: list[str] = []
    for truth_index, truth in enumerate(truth_regions):
        best_id = ""
        best_iou = threshold
        for region in unused:
            if page_index.get(region.pageId, -1) != truth.page_index:
                continue
            if _dominant_label(region) != truth.label:
                continue
            score = iou(as_rect(region.geometry), truth.rect)
            if score >= best_iou:
                best_iou = score
                best_id = region.id
        if not best_id:
            continue
        matched_truth.append(truth_index)
        matched_ids.append(best_id)
        unused = [region for region in unused if region.id != best_id]
    return matched_truth, matched_ids


def labeled_region_metrics(
    truth_regions: list[TruthRegion],
    layout: generated.LayoutDocument,
) -> OrderMetrics:
    """Precision/recall from region-level boxes; ordering still uses match order."""
    matched_truth, matched_ids = region_iou_matches(truth_regions, layout)
    recovered = [region for region in layout.regions if region.kind not in _FURNITURE_KINDS]
    flow_position = {region_id: index for index, region_id in enumerate(layout.primaryFlow)}
    positions = [
        flow_position[region_id] for region_id in matched_ids if region_id in flow_position
    ]
    pairs_total = 0
    pairs_correct = 0
    for i in range(len(positions)):
        for j in range(i + 1, len(positions)):
            pairs_total += 1
            if positions[i] < positions[j]:
                pairs_correct += 1
    pairwise = pairs_correct / pairs_total if pairs_total else 1.0
    return OrderMetrics(
        region_recall=len(matched_truth) / len(truth_regions) if truth_regions else 1.0,
        region_precision=len(matched_ids) / len(recovered) if recovered else 1.0,
        pairwise_ordering_accuracy=round(pairwise, 4),
        sequence_accuracy=positions == sorted(positions),
        matched_regions=len(matched_truth),
        truth_regions=len(truth_regions),
        recovered_regions=len(recovered),
    )


def label_accuracy(
    truth_regions: list[TruthRegion],
    layout: generated.LayoutDocument,
    label: str,
) -> float | None:
    """Recall of one LayoutLabel against recovered regions; None when no GT of that label.

    This is layout-label recall, not paragraph merge/split accuracy or
    section-tree / heading-level accuracy.
    """
    subset = [region for region in truth_regions if region.label == label]
    if not subset:
        return None
    matched_truth, _matched_ids = region_iou_matches(subset, layout)
    return round(len(matched_truth) / len(subset), 4)


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
    labeled = parse_truth_regions(truth_data.get("regions"))
    raw_snippets: Any = truth_data.get("readingOrder")
    snippet_list = cast("list[Any]", raw_snippets) if isinstance(raw_snippets, list) else []
    snippets = [str(snippet) for snippet in snippet_list]
    order = (
        labeled_region_metrics(labeled, layout)
        if labeled
        else order_metrics(snippets, list(layout.primaryFlow), region_texts)
    )
    semantic_truth: dict[str, Any] = truth_data.get("semantic") or {}
    return {
        "physicalTextCoverage": physical_text_coverage(physical, region_texts),
        "regionRecall": round(order.region_recall, 4),
        "regionPrecision": round(order.region_precision, 4),
        "pairwiseOrderingAccuracy": order.pairwise_ordering_accuracy,
        "sequenceAccuracy": order.sequence_accuracy,
        "paragraphLabelRecall": label_accuracy(labeled, layout, "PARAGRAPH_LIKE")
        if labeled
        else None,
        "headingLabelRecall": label_accuracy(labeled, layout, "HEADING_LIKE") if labeled else None,
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


def export_seed_truth_regions(
    layout: generated.LayoutDocument,
    region_texts: dict[str, str],
    reading_order: list[str],
) -> list[dict[str, object]]:
    """Seed labeled boxes from snippet matches plus figure/table/formula regions.

    Used to draft layout-truth ``regions[]``; keep only reviewed boxes.
    """
    _matched_truth, matched_ids = region_matches(reading_order, region_texts)
    keep = set(matched_ids)
    for region in layout.regions:
        if region.kind in {"FIGURE", "TABLE", "FORMULA"}:
            keep.add(region.id)
    page_index = {page.pageId: index for index, page in enumerate(layout.pages)}
    exported: list[dict[str, object]] = []
    for region in layout.regions:
        if region.id not in keep or region.kind in _FURNITURE_KINDS:
            continue
        rect = as_rect(region.geometry)
        exported.append(
            {
                "pageIndex": page_index.get(region.pageId, 0),
                "label": _dominant_label(region),
                "geometry": {
                    "kind": "rect",
                    "x": round(rect.x, 2),
                    "y": round(rect.y, 2),
                    "width": round(rect.width, 2),
                    "height": round(rect.height, 2),
                },
                "textPreview": region_texts.get(region.id, "")[:80],
            }
        )
    return exported
