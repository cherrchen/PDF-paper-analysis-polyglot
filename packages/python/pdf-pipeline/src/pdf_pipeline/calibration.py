"""Phase 7.5 Confidence Calibration: make confidence numbers meaningful.

System confidence must be interpretable (roadmap Phase 7.5): a region
fused at 0.9 should be right more often than one fused at 0.6. The
calibration harness measures exactly that on benchmark truth: for every
recovered text region we record its dominant label confidence and
whether the region matches the hand truth, then bucket the pairs. If
accuracy does not rise with the buckets, the fusion confidence formula
— not the report — needs adjusting (evidence first, constants second).
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import TYPE_CHECKING

from pdf_pipeline.metrics import parse_truth_regions, region_iou_matches, region_matches

if TYPE_CHECKING:
    from collections.abc import Sequence

    from document_model.generated import schema_models as generated

# Confidence buckets: [lower, upper) with the last bin closed.
BIN_EDGES: tuple[float, ...] = (0.0, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0)


@dataclass(frozen=True)
class CalibrationBin:
    """Correctness of one confidence bucket."""

    lower: float
    upper: float
    total: int
    correct: int

    @property
    def accuracy(self) -> float:
        return self.correct / self.total if self.total else 0.0

    def to_json(self) -> dict[str, float | int]:
        return {
            "lower": self.lower,
            "upper": self.upper,
            "total": self.total,
            "correct": self.correct,
            "accuracy": round(self.accuracy, 4),
        }


@dataclass(frozen=True)
class CalibrationReport:
    """Bucketed confidence-vs-correctness over a benchmark corpus."""

    bins: tuple[CalibrationBin, ...]
    total: int
    correct: int

    @property
    def accuracy(self) -> float:
        return self.correct / self.total if self.total else 0.0

    @property
    def monotonic(self) -> bool:
        """True when accuracy does not decrease as confidence rises."""
        accuracies = [b.accuracy for b in self.bins if b.total > 0]
        return all(a <= b + 0.05 for a, b in itertools.pairwise(accuracies))

    def to_json(self) -> dict[str, object]:
        return {
            "bins": [b.to_json() for b in self.bins],
            "total": self.total,
            "correct": self.correct,
            "accuracy": round(self.accuracy, 4),
            "monotonic": self.monotonic,
        }


def calibration_samples(
    layout: generated.LayoutDocument,
    region_texts: dict[str, str],
    truth_snippets: list[str],
    truth_regions: list[object] | None = None,
) -> list[tuple[float, bool]]:
    """(dominant-label confidence, matched-to-truth) per evaluated region.

    When region-level boxes exist, correctness is IoU+label match. Otherwise
    snippet matching is used and extra recovered regions look like negatives.
    """
    labeled = parse_truth_regions(truth_regions)
    if labeled:
        _matched_truth, matched_regions = region_iou_matches(labeled, layout)
        scored_ids = {
            region.id for region in layout.regions if region.kind not in {"HEADER", "FOOTER"}
        }
    else:
        _matched_truth, matched_regions = region_matches(truth_snippets, region_texts)
        scored_ids = set(layout.primaryFlow)
    matched = set(matched_regions)
    samples: list[tuple[float, bool]] = []
    for region in layout.regions:
        if region.id not in scored_ids:
            continue
        text = region_texts.get(region.id, "")
        if not labeled and (not text.strip() or not region.labels):
            continue
        if not region.labels:
            continue
        samples.append((region.labels[0].confidence, region.id in matched))
    return samples


def calibrate(samples: Sequence[tuple[float, bool]]) -> CalibrationReport:
    """Bucket confidence/correctness pairs into the shared bin edges."""
    bins = [[0, 0] for _ in range(len(BIN_EDGES) - 1)]
    for confidence, correct in samples:
        index = _bucket_index(confidence)
        bins[index][0] += 1
        if correct:
            bins[index][1] += 1
    report_bins = tuple(
        CalibrationBin(lower=BIN_EDGES[i], upper=BIN_EDGES[i + 1], total=t, correct=c)
        for i, (t, c) in enumerate(bins)
    )
    total = sum(b.total for b in report_bins)
    correct = sum(b.correct for b in report_bins)
    return CalibrationReport(bins=report_bins, total=total, correct=correct)


def _bucket_index(confidence: float) -> int:
    for index in range(len(BIN_EDGES) - 1):
        lower, upper = BIN_EDGES[index], BIN_EDGES[index + 1]
        if index == len(BIN_EDGES) - 2 and confidence <= upper:
            return index
        if lower <= confidence < upper:
            return index
    return len(BIN_EDGES) - 2
