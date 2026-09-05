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

from dataclasses import dataclass

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

    ``region_texts`` maps layout region id -> recovered text; snippets
    only present in excluded regions (footers, footnotes) count against
    recall, matching the exit gate's content-completeness priority.
    """
    matched_truth, matched_regions = region_matches(truth_snippets, region_texts)

    flow_position = {region_id: index for index, region_id in enumerate(primary_flow)}
    positions = [
        flow_position[region_id] for region_id in matched_regions if region_id in flow_position
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
        region_recall=len(matched_truth) / len(truth_snippets) if truth_snippets else 1.0,
        region_precision=len(matched_truth) / len(region_texts) if region_texts else 1.0,
        pairwise_ordering_accuracy=round(pairwise, 4),
        sequence_accuracy=positions == sorted(positions),
        matched_regions=len(matched_truth),
        truth_regions=len(truth_snippets),
        recovered_regions=len(region_texts),
    )


__all__ = ["OrderMetrics", "order_metrics", "region_matches"]
