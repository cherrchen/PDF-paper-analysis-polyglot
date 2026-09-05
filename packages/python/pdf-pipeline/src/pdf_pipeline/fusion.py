"""Phase 3.2 region fusion: normalized evidence + internal blocks -> regions.

Multiple sources describe the same page: the deterministic geometric
blocking of PhysicalDocument lines, and one or more provider candidate
sets. Fusion decides which descriptions talk about the same region
(candidate matching) and converges them into one internal region with a
weighted label, fused confidence, and full evidence provenance.

Design constraints (Roadmap §4 Step 4): deterministic baseline only — no
LLM, no optimizer. Every fusion output carries the reason it was chosen so
wrong fusions are observable (Roadmap §4 Step 5).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from document_model.generated import schema_models as generated

from pdf_pipeline.evidence.normalize import MATCH_KEY_QUANTUM_PT, NormalizedCandidate
from pdf_pipeline.geometry import (
    containment,
    iou,
    union_rect,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

# Candidate matching thresholds.
MATCH_IOU = 0.4
MATCH_CONTAINMENT = 0.7
MATCH_TEXT_OVERLAP = 0.5

# Confidence weighting: a matched internal block and its evidence converge
# on a label; agreement boosts confidence, disagreement keeps both hints.
_LABEL_AGREEMENT_BOOST = 0.15
_FUSION_BASE_SCORE = 0.7

_TOKEN_PATTERN = re.compile(r"\w+", re.UNICODE)


@dataclass(frozen=True)
class RegionLine:
    """One physical line inside a region, with geometry for heuristics."""

    text: str
    rect: generated.Rect
    font_size: float


@dataclass(frozen=True)
class InternalRegion:
    """Fusion output: one page region before LayoutDocument assembly.

    ``kind`` is the visual region kind; ``labels`` keep the full hypothesis
    list (geometric and provider-backed) for observability. ``lines``
    preserve the ordered physical spans so text assembly, continuation
    heuristics, and mapping keep reading order inside the region.
    """

    region_id: str
    page_id: str
    rect: generated.Rect
    kind: generated.LayoutRegionKind
    labels: list[generated.LayoutLabelCandidate]
    confidence: generated.LayoutConfidence
    physical_object_ids: list[str] = field(default_factory=list[str])
    evidence_ids: list[str] = field(default_factory=list[str])
    lines: list[RegionLine] = field(default_factory=list[RegionLine])
    # Band/column membership assigned during geometric blocking
    # (page_structure); None when the region came from evidence only.
    column_tag: tuple[int, int] | None = None

    @property
    def text(self) -> str:
        """Ordered region text."""
        return " ".join(line.text for line in self.lines if line.text)

    @property
    def font_size(self) -> float:
        """Largest line font size in the region (heading/caption signal)."""
        return max((line.font_size for line in self.lines), default=0.0)

    @property
    def last_line(self) -> RegionLine | None:
        return self.lines[-1] if self.lines else None

    @property
    def first_line(self) -> RegionLine | None:
        return self.lines[0] if self.lines else None


def _tokens(text: str) -> set[str]:
    return set(_TOKEN_PATTERN.findall(text.lower()))


def text_overlap_ratio(a: str, b: str) -> float:
    """Token-level Jaccard-style overlap between two text snippets."""
    tokens_a = _tokens(a)
    tokens_b = _tokens(b)
    if not tokens_a or not tokens_b:
        return 0.0
    return len(tokens_a & tokens_b) / min(len(tokens_a), len(tokens_b))


_LABEL_SIMILARITY: dict[tuple[str, str], float] = {
    # (label_a, label_b) -> similarity in [0, 1]; symmetric via lookup.
    ("TEXT", "TEXT"): 1.0,
    ("TEXT", "PARAGRAPH_LIKE"): 0.9,
    ("TEXT", "HEADING_LIKE"): 0.5,
    ("TEXT", "CAPTION_LIKE"): 0.5,
    ("TEXT", "FOOTNOTE"): 0.5,
    ("TEXT", "LIST"): 0.7,
    ("PARAGRAPH_LIKE", "PARAGRAPH_LIKE"): 1.0,
    ("PARAGRAPH_LIKE", "HEADING_LIKE"): 0.5,
    ("PARAGRAPH_LIKE", "CAPTION_LIKE"): 0.5,
    ("PARAGRAPH_LIKE", "FOOTNOTE"): 0.5,
    ("PARAGRAPH_LIKE", "LIST"): 0.7,
    ("HEADING_LIKE", "HEADING_LIKE"): 1.0,
    ("HEADING_LIKE", "CAPTION_LIKE"): 0.3,
    ("CAPTION_LIKE", "CAPTION_LIKE"): 1.0,
    ("FOOTNOTE", "FOOTNOTE"): 1.0,
    ("LIST", "LIST"): 1.0,
    ("FIGURE", "FIGURE"): 1.0,
    ("TABLE", "TABLE"): 1.0,
    ("FORMULA", "FORMULA"): 1.0,
    ("FIGURE", "TABLE"): 0.3,
    ("HEADER", "HEADER"): 1.0,
    ("FOOTER", "FOOTER"): 1.0,
    ("HEADER", "HEADING_LIKE"): 0.3,
    ("UNKNOWN", "UNKNOWN"): 1.0,
}


def label_similarity(a: str, b: str) -> float:
    """Similarity of two normalized labels; 0 for incompatible kinds."""
    if a == b:
        return 1.0
    return _LABEL_SIMILARITY.get((a, b), _LABEL_SIMILARITY.get((b, a), 0.0))


@dataclass(frozen=True)
class MatchResult:
    """Why a candidate matches an internal region (observability)."""

    score: float
    via: str


def match_candidate(
    candidate: NormalizedCandidate,
    *,
    rect: generated.Rect,
    label: str,
    text: str = "",
    ignore_label: bool = False,
) -> MatchResult | None:
    """Score a provider candidate against an internal region description.

    Matching requires geometric agreement (IoU or containment) and label
    compatibility; overlapping text strengthens the match when previews are
    available. Returns ``None`` when the candidate describes a different
    region. Structured candidates (TABLE/FORMULA) match geometrically:
    their content sits inside text blocks the baseline labels as
    paragraph-like.
    """
    similarity = 1.0 if ignore_label else label_similarity(candidate.label, label)
    if similarity <= 0.0:
        return None
    geometry_iou = iou(candidate.rect, rect)
    geometry_containment = max(containment(candidate.rect, rect), containment(rect, candidate.rect))
    via_parts: list[str] = []
    score = 0.0
    if geometry_iou >= MATCH_IOU:
        score = max(score, geometry_iou)
        via_parts.append(f"iou={geometry_iou:.2f}")
    if geometry_containment >= MATCH_CONTAINMENT:
        score = max(score, geometry_containment)
        via_parts.append(f"containment={geometry_containment:.2f}")
    if score <= 0.0:
        return None
    quantized = (
        candidate.pageId,
        round(rect.x / MATCH_KEY_QUANTUM_PT),
        round(rect.y / MATCH_KEY_QUANTUM_PT),
        candidate.label,
    )
    if candidate.match_key()[:3] == quantized[:3]:
        via_parts.append("match_key")
    if candidate.textPreview and text:
        text_overlap = text_overlap_ratio(candidate.textPreview, text)
        if text_overlap >= MATCH_TEXT_OVERLAP:
            score = max(score, 0.5 + 0.5 * text_overlap)
            via_parts.append(f"text={text_overlap:.2f}")
    score *= similarity
    if score <= 0.0:
        return None
    return MatchResult(score=min(score, 1.0), via="+".join(via_parts))


def fuse_candidate_labels(
    candidates: list[NormalizedCandidate],
) -> tuple[generated.LayoutLabel, float]:
    """Confidence-weighted label vote across matching candidates."""
    totals: dict[str, float] = {}
    for candidate in candidates:
        totals[candidate.label] = totals.get(candidate.label, 0.0) + candidate.confidence
    best_label = max(totals, key=lambda label: (totals[label], label))
    total = sum(totals.values())
    share = totals[best_label] / total if total > 0 else 0.0
    return cast("generated.LayoutLabel", best_label), share


@dataclass
class RegionDraft:
    """Mutable accumulator used while fusing sources into one region."""

    page_id: str
    rect: generated.Rect
    kind: generated.LayoutRegionKind
    physical_object_ids: list[str]
    lines: list[RegionLine]
    label_hypotheses: list[tuple[str, float]]  # (label, confidence)
    evidence_ids: list[str]
    match_notes: list[str]
    column_tag: tuple[int, int] | None = None

    def add_label(self, label: str, confidence: float) -> None:
        self.label_hypotheses.append((label, confidence))

    def cover(self, rect: generated.Rect) -> None:
        self.rect = union_rect(self.rect, rect)

    def add_lines(self, lines: list[RegionLine]) -> None:
        """Merge in lines, keeping page reading order (y, then x)."""
        self.lines.extend(lines)
        self.lines.sort(key=lambda line: (line.rect.y, line.rect.x, line.text))


_KIND_BY_LABEL: dict[str, generated.LayoutRegionKind] = {
    "TEXT": "TEXT",
    "PARAGRAPH_LIKE": "TEXT",
    "HEADING_LIKE": "TEXT",
    "CAPTION_LIKE": "TEXT",
    "LIST": "TEXT",
    "FOOTNOTE": "FOOTNOTE",
    "FIGURE": "FIGURE",
    "TABLE": "TABLE",
    "FORMULA": "FORMULA",
    "HEADER": "HEADER",
    "FOOTER": "FOOTER",
    "UNKNOWN": "TEXT",
}


def kind_for_label(label: str) -> generated.LayoutRegionKind:
    """Visual region kind for a normalized label."""
    return _KIND_BY_LABEL.get(label, "TEXT")


def draft_region(
    *,
    region_id: str,
    page_id: str,
    rect: generated.Rect,
    label: str,
    confidence: float,
    physical_object_ids: Iterable[str] = (),
    lines: Iterable[RegionLine] = (),
    column_tag: tuple[int, int] | None = None,
    reason: str,
) -> RegionDraft:
    """Start a region draft from one internal source (geometry or evidence)."""
    return RegionDraft(
        page_id=page_id,
        rect=rect,
        kind=kind_for_label(label),
        physical_object_ids=list(physical_object_ids),
        lines=list(lines),
        label_hypotheses=[(label, confidence)],
        evidence_ids=[],
        match_notes=[reason],
        column_tag=column_tag,
    )


def fuse_matched_candidates(
    draft: RegionDraft,
    matches: list[tuple[NormalizedCandidate, MatchResult]],
) -> None:
    """Fold matched provider candidates into a region draft.

    Geometry: union rect (provider may see the region slightly larger).
    Label: the weighted vote joins the hypothesis list; agreement with the
    draft's dominant label boosts final confidence. Evidence ids and the
    match reason are recorded for observability.
    """
    if not matches:
        return
    fused_label, fused_share = fuse_candidate_labels([candidate for candidate, _ in matches])
    dominant = max(
        ((label, weight) for label, weight in draft.label_hypotheses),
        key=lambda item: item[1],
    )
    draft.add_label(fused_label, fused_share)
    draft.kind = kind_for_label(fused_label)
    for candidate, match in matches:
        draft.cover(candidate.rect)
        draft.evidence_ids.append(candidate.evidenceId)
        draft.match_notes.append(f"evidence:{candidate.provider}:{match.via}")
        if label_similarity(candidate.label, dominant[0]) >= 0.9:
            draft.label_hypotheses.append((dominant[0], _LABEL_AGREEMENT_BOOST))


def finalize_draft(draft: RegionDraft, region_id: str) -> InternalRegion:
    """Convert an accumulator into the immutable fusion output."""
    _, best_weight = max(draft.label_hypotheses, key=lambda item: (item[1], item[0]))
    # Multiple agreeing sources push the score up; cap at 0.95: layout
    # recovery is never certain (Roadmap quality priority).
    score = min(0.95, _FUSION_BASE_SCORE + 0.1 * len(draft.evidence_ids) + 0.2 * best_weight)
    labels = [
        generated.LayoutLabelCandidate(
            label=cast("generated.LayoutLabel", label),
            confidence=round(min(weight, 1.0), 4),
            evidenceIds=[],
        )
        for label, weight in draft.label_hypotheses
    ]
    # Dominant label first, rest stable by weight.
    labels.sort(key=lambda candidate: (-candidate.confidence, candidate.label))
    deduplicated: list[generated.LayoutLabelCandidate] = []
    seen: set[str] = set()
    for candidate in labels:
        if candidate.label in seen:
            continue
        seen.add(candidate.label)
        deduplicated.append(candidate)
    return InternalRegion(
        region_id=region_id,
        page_id=draft.page_id,
        rect=draft.rect,
        kind=draft.kind,
        labels=deduplicated,
        confidence=generated.LayoutConfidence(
            score=round(score, 4),
            reason="; ".join(draft.match_notes),
        ),
        physical_object_ids=list(draft.physical_object_ids),
        evidence_ids=list(draft.evidence_ids),
        lines=list(draft.lines),
        column_tag=draft.column_tag,
    )


def dominant_label(region: InternalRegion) -> str:
    """The region's highest-confidence label."""
    if not region.labels:
        return "UNKNOWN"
    return region.labels[0].label


# Structured candidates absorb overlapping text blocks instead of merely
# voting on labels: table cells and formula lines are one region.
_STRUCTURED_LABELS = {"TABLE", "FORMULA"}
# Weight of a structured candidate over text-block label hypotheses.
_STRUCTURED_WEIGHT = 1.5


def _draft_label(draft: RegionDraft) -> str:
    return max(draft.label_hypotheses, key=lambda item: item[1])[0]


def _draft_text(draft: RegionDraft) -> str:
    return " ".join(line.text for line in draft.lines)


def fuse_page(
    *,
    drafts: list[RegionDraft],
    candidates: list[NormalizedCandidate],
    region_id_fn: Callable[[int], str],
) -> list[InternalRegion]:
    """Fuse one page's geometric drafts with normalized provider candidates.

    Deterministic order: structured candidates (TABLE/FORMULA) absorb the
    text blocks they cover; remaining text candidates fold into their best
    matching block as weighted label evidence; candidates matching nothing
    become evidence-only regions. Final ids are assigned in page reading
    order so repeated runs are byte-identical.
    """
    ordered = sorted(
        candidates,
        key=lambda candidate: (
            0 if candidate.label in _STRUCTURED_LABELS else 1,
            -candidate.confidence,
            candidate.evidenceId,
        ),
    )
    open_drafts = list(drafts)
    consumed_candidates: set[str] = set()
    structured_rects: list[generated.Rect] = []

    for candidate in ordered:
        structured = candidate.label in _STRUCTURED_LABELS
        matches: list[tuple[RegionDraft, MatchResult]] = []
        for draft in open_drafts:
            match = match_candidate(
                candidate,
                rect=draft.rect,
                label=_draft_label(draft),
                text=_draft_text(draft),
                ignore_label=structured,
            )
            if match is not None:
                matches.append((draft, match))

        if structured:
            if matches:
                base = matches[0][0]
                for draft, _ in matches[1:]:
                    base.physical_object_ids.extend(draft.physical_object_ids)
                    base.add_lines(draft.lines)
                    base.label_hypotheses.extend(draft.label_hypotheses)
                    base.match_notes.extend(draft.match_notes)
                    base.cover(draft.rect)
                    open_drafts.remove(draft)
                base.add_label(candidate.label, _STRUCTURED_WEIGHT)
                base.kind = kind_for_label(candidate.label)
                base.cover(candidate.rect)
                base.evidence_ids.append(candidate.evidenceId)
                base.match_notes.append(
                    f"evidence:{candidate.provider}:structured:{candidate.providerLabel}"
                )
                structured_rects.append(candidate.rect)
                consumed_candidates.add(candidate.evidenceId)
                continue
            # No internal block matched: the candidate still describes a
            # region, and cell noise inside it must be suppressed below.
            structured_rects.append(candidate.rect)

        # Text candidates inside an absorbed structured region are cell
        # noise; drop them. Structured candidates own their rects and pass.
        if not structured and any(
            containment(rect, candidate.rect) >= MATCH_CONTAINMENT for rect in structured_rects
        ):
            consumed_candidates.add(candidate.evidenceId)
            continue
        if matches:
            # Deterministic tiebreak: reading-order draft position wins.
            best_index = max(
                range(len(matches)),
                key=lambda index: (matches[index][1].score, -index),
            )
            best_draft, best_match = matches[best_index]
            fuse_matched_candidates(best_draft, [(candidate, best_match)])
            consumed_candidates.add(candidate.evidenceId)
            continue

        # Unmatched evidence becomes its own draft: providers may see
        # regions the geometric baseline missed. Dropping them would lose
        # recall (Roadmap Phase 3.2 validation).
        evidence_draft = draft_region(
            region_id="pending",
            page_id=candidate.pageId,
            rect=candidate.rect,
            label=candidate.label,
            confidence=candidate.confidence,
            reason=f"evidence-only:{candidate.provider}:{candidate.providerLabel}",
        )
        evidence_draft.evidence_ids.append(candidate.evidenceId)
        open_drafts.append(evidence_draft)

    open_drafts.sort(key=lambda draft: (draft.rect.y, draft.rect.x, _draft_text(draft)))
    return [
        finalize_draft(draft, region_id_fn(ordinal)) for ordinal, draft in enumerate(open_drafts)
    ]


__all__ = [
    "InternalRegion",
    "MatchResult",
    "RegionLine",
    "dominant_label",
    "draft_region",
    "finalize_draft",
    "fuse_candidate_labels",
    "fuse_matched_candidates",
    "kind_for_label",
    "label_similarity",
    "match_candidate",
    "text_overlap_ratio",
]
