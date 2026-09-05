"""Benchmark metrics tests (Roadmap M3 Validation + §6 Benchmark Policy)."""

from __future__ import annotations

from pdf_pipeline.metrics import order_metrics, region_matches


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
