"""Benchmark metrics tests (Roadmap M3 Validation + §6 Benchmark Policy)."""

from __future__ import annotations

from pdf_pipeline.metrics import (
    labeled_region_metrics,
    order_metrics,
    region_iou_matches,
    region_matches,
)


def test_region_matches_respects_hyphens_and_case() -> None:
    texts = {
        "r1": "Two-Column Fixture",
        "r2": "This fixture exercises a standard two-column article layout.",
    }
    matched_truth, matched_regions = region_matches(
        ["two column fixture", "this fixture exercises"], texts
    )
    assert matched_truth == [0, 1]
    assert matched_regions == ["r1", "r2"]


def test_region_matches_is_greedy_one_to_one() -> None:
    texts = {"r1": "same snippet text", "r2": "other content"}
    matched_truth, matched_regions = region_matches(["same snippet", "same snippet again"], texts)
    assert matched_truth == [0]
    assert matched_regions == ["r1"]


def test_order_metrics_perfect_flow() -> None:
    texts = {"a": "first region", "b": "second region", "c": "third region"}
    metrics = order_metrics(
        ["first region", "second region", "third region"], ["a", "b", "c"], texts
    )
    assert metrics.region_recall == 1.0
    assert metrics.pairwise_ordering_accuracy == 1.0
    assert metrics.sequence_accuracy is True


def test_order_metrics_detects_inversions() -> None:
    texts = {"a": "first region", "b": "second region"}
    metrics = order_metrics(["first region", "second region"], ["b", "a"], texts)
    assert metrics.region_recall == 1.0
    assert metrics.pairwise_ordering_accuracy == 0.0
    assert metrics.sequence_accuracy is False


def test_order_metrics_empty_truth() -> None:
    metrics = order_metrics([], ["a"], {"a": "text"})
    assert metrics.region_recall == 1.0
    assert metrics.sequence_accuracy is True


def test_region_iou_matches_label_and_geometry() -> None:
    from document_model.generated import schema_models as generated
    from pdf_pipeline.metrics import TruthRegion

    page_id = "00000000-0000-0000-0000-0000000000aa"
    recovered = generated.LayoutRegion(
        id="00000000-0000-0000-0000-0000000000bb",
        pageId=page_id,
        geometry=generated.Rect(kind="rect", x=10, y=10, width=80, height=20),
        kind="TEXT",
        childIds=[],
        physicalObjectIds=[],
        labels=[
            generated.LayoutLabelCandidate(label="PARAGRAPH_LIKE", confidence=0.9, evidenceIds=[])
        ],
        confidence=generated.LayoutConfidence(score=0.9, reason="test"),
        provenanceIds=[],
    )
    extra = generated.LayoutRegion(
        id="00000000-0000-0000-0000-0000000000cc",
        pageId=page_id,
        geometry=generated.Rect(kind="rect", x=10, y=200, width=80, height=20),
        kind="TEXT",
        childIds=[],
        physicalObjectIds=[],
        labels=[
            generated.LayoutLabelCandidate(label="HEADING_LIKE", confidence=0.8, evidenceIds=[])
        ],
        confidence=generated.LayoutConfidence(score=0.8, reason="test"),
        provenanceIds=[],
    )
    layout = generated.LayoutDocument(
        schemaVersion="0.1.0",
        id="00000000-0000-0000-0000-0000000000dd",
        physicalDocumentId="00000000-0000-0000-0000-0000000000ee",
        pages=[
            generated.LayoutPage(pageId=page_id, regionIds=[recovered.id, extra.id], bandIds=[])
        ],
        regions=[recovered, extra],
        bands=[],
        columns=[],
        groups=[],
        readingFlow=generated.ReadingFlowGraph(nodes=[recovered.id, extra.id], edges=[]),
        primaryFlow=[recovered.id, extra.id],
    )
    truth = [
        TruthRegion(
            page_index=0,
            label="PARAGRAPH_LIKE",
            rect=generated.Rect(kind="rect", x=12, y=12, width=76, height=18),
        )
    ]
    matched_truth, matched_ids = region_iou_matches(truth, layout)
    assert matched_truth == [0]
    assert matched_ids == [recovered.id]
    metrics = labeled_region_metrics(truth, layout)
    assert metrics.region_recall == 1.0
    assert metrics.region_precision == 0.5


def test_label_accuracy_is_layout_recall() -> None:
    from document_model.generated import schema_models as generated
    from pdf_pipeline.metrics import TruthRegion, label_accuracy

    page_id = "00000000-0000-0000-0000-0000000000aa"
    recovered = generated.LayoutRegion(
        id="00000000-0000-0000-0000-0000000000bb",
        pageId=page_id,
        geometry=generated.Rect(kind="rect", x=10, y=10, width=80, height=20),
        kind="TEXT",
        childIds=[],
        physicalObjectIds=[],
        labels=[
            generated.LayoutLabelCandidate(label="PARAGRAPH_LIKE", confidence=0.9, evidenceIds=[])
        ],
        confidence=generated.LayoutConfidence(score=0.9, reason="test"),
        provenanceIds=[],
    )
    layout = generated.LayoutDocument(
        schemaVersion="0.1.0",
        id="00000000-0000-0000-0000-0000000000dd",
        physicalDocumentId="00000000-0000-0000-0000-0000000000ee",
        pages=[generated.LayoutPage(pageId=page_id, regionIds=[recovered.id], bandIds=[])],
        regions=[recovered],
        bands=[],
        columns=[],
        groups=[],
        readingFlow=generated.ReadingFlowGraph(nodes=[recovered.id], edges=[]),
        primaryFlow=[recovered.id],
    )
    truth = [
        TruthRegion(
            page_index=0,
            label="PARAGRAPH_LIKE",
            rect=generated.Rect(kind="rect", x=12, y=12, width=76, height=18),
        )
    ]
    assert label_accuracy(truth, layout, "PARAGRAPH_LIKE") == 1.0
    assert label_accuracy(truth, layout, "HEADING_LIKE") is None
