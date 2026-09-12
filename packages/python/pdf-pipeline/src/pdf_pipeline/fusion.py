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

from pdf_pipeline.capabilities import Registry, authority_rank
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

# Phase 7.4 conflict resolution: capability authority beats vote counting
# (docs/architecture/document-architecture.md §43 forbids majority voting).
# A candidate's vote is its confidence scaled by the provider's authority
# rank for the candidate's capability: primary > challenger > fallback >
# unlisted. With no registry the plain confidence vote applies.
AUTHORITY_WEIGHT_PRIMARY = 1.5
AUTHORITY_WEIGHT_CHALLENGER = 1.2
AUTHORITY_WEIGHT_FALLBACK = 1.0
NON_AUTHORITY_WEIGHT = 0.8
_RANK_WEIGHTS = {
    0: AUTHORITY_WEIGHT_PRIMARY,
    1: AUTHORITY_WEIGHT_CHALLENGER,
    2: AUTHORITY_WEIGHT_FALLBACK,
}
_LABEL_CAPABILITY = {"TABLE": "table.structure", "FORMULA": "formula.detection"}
_DEFAULT_CAPABILITY = "layout.region"


def capability_for_label(label: str) -> str:
    """Capability whose authority decides a label conflict."""
    return _LABEL_CAPABILITY.get(label, _DEFAULT_CAPABILITY)


def authority_weight(registry: Registry, label: str, provider: str) -> float:
    """Confidence multiplier for a provider's vote on a label.

    Role-based (not compact index after empty slots): primary 1.5,
    challenger 1.2, fallback 1.0, unlisted 0.8. Empty challenger/fallback
    slots must not promote a later role or an unlisted provider.
    """
    rank = authority_rank(registry, capability_for_label(label), provider)
    return _RANK_WEIGHTS.get(rank, NON_AUTHORITY_WEIGHT)


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
    *,
    registry: Registry | None = None,
) -> tuple[generated.LayoutLabel, float]:
    """Authority- and confidence-weighted label vote across candidates."""
    totals: dict[str, float] = {}
    for candidate in candidates:
        weight = candidate.confidence
        if registry is not None:
            weight *= authority_weight(registry, candidate.label, candidate.provider)
        totals[candidate.label] = totals.get(candidate.label, 0.0) + weight
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
    *,
    registry: Registry | None = None,
) -> None:
    """Fold matched provider candidates into a region draft.

    Geometry: union rect (provider may see the region slightly larger).
    Label: the weighted vote joins the hypothesis list; agreement with the
    draft's dominant label boosts final confidence. Evidence ids and the
    match reason are recorded for observability.
    """
    if not matches:
        return
    fused_label, fused_share = fuse_candidate_labels(
        [candidate for candidate, _ in matches], registry=registry
    )
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


def _draft_label(draft: RegionDraft) -> str:
    return max(draft.label_hypotheses, key=lambda item: item[1])[0]


def _draft_text(draft: RegionDraft) -> str:
    return " ".join(line.text for line in draft.lines)


def _absorb_draft(base: RegionDraft, extra: RegionDraft) -> None:
    """Merge one draft's geometry, lines, and hypotheses into another."""
    base.physical_object_ids.extend(extra.physical_object_ids)
    base.add_lines(extra.lines)
    base.label_hypotheses.extend(extra.label_hypotheses)
    base.match_notes.extend(extra.match_notes)
    base.cover(extra.rect)
    if base.column_tag is None:
        base.column_tag = extra.column_tag


def _matching_drafts(
    candidate: NormalizedCandidate,
    open_drafts: list[RegionDraft],
    *,
    ignore_label: bool,
) -> list[tuple[RegionDraft, MatchResult]]:
    matches: list[tuple[RegionDraft, MatchResult]] = []
    for draft in open_drafts:
        match = match_candidate(
            candidate,
            rect=draft.rect,
            label=_draft_label(draft),
            text=_draft_text(draft),
            ignore_label=ignore_label,
        )
        if match is not None:
            matches.append((draft, match))
    return matches


def _candidates_overlap(left: NormalizedCandidate, right: NormalizedCandidate) -> bool:
    """True when two provider candidates describe the same visual region."""
    return (
        match_candidate(
            left,
            rect=right.rect,
            label=right.label,
            text=right.textPreview,
            ignore_label=True,
        )
        is not None
    )


@dataclass
class _CandidateCluster:
    """Candidates that describe one region, awaiting a single authority vote."""

    candidates: list[NormalizedCandidate]
    base: RegionDraft | None


def _find_cluster(
    candidate: NormalizedCandidate,
    matches: list[tuple[RegionDraft, MatchResult]],
    clusters: list[_CandidateCluster],
) -> _CandidateCluster | None:
    matched_ids = {id(draft) for draft, _ in matches}
    for cluster in clusters:
        if cluster.base is not None and id(cluster.base) in matched_ids:
            return cluster
        if any(_candidates_overlap(candidate, other) for other in cluster.candidates):
            return cluster
    return None


def _attach_structured(
    candidate: NormalizedCandidate,
    matches: list[tuple[RegionDraft, MatchResult]],
    cluster: _CandidateCluster,
    open_drafts: list[RegionDraft],
) -> None:
    cluster.candidates.append(candidate)
    for draft, _ in matches:
        if cluster.base is None:
            cluster.base = draft
            continue
        if draft is not cluster.base and draft in open_drafts:
            _absorb_draft(cluster.base, draft)
            open_drafts.remove(draft)


def _new_structured_cluster(
    candidate: NormalizedCandidate,
    matches: list[tuple[RegionDraft, MatchResult]],
    open_drafts: list[RegionDraft],
) -> _CandidateCluster:
    if not matches:
        return _CandidateCluster(candidates=[candidate], base=None)
    base = matches[0][0]
    for extra, _ in matches[1:]:
        _absorb_draft(base, extra)
        open_drafts.remove(extra)
    return _CandidateCluster(candidates=[candidate], base=base)


def _apply_structured_cluster(
    cluster: _CandidateCluster,
    open_drafts: list[RegionDraft],
    *,
    registry: Registry | None,
) -> generated.Rect:
    """Vote among clustered structured candidates and stamp the winner."""
    fused_label, fused_share = fuse_candidate_labels(cluster.candidates, registry=registry)
    first = cluster.candidates[0]
    base = cluster.base
    if base is None:
        base = draft_region(
            region_id="pending",
            page_id=first.pageId,
            rect=first.rect,
            label=fused_label,
            confidence=fused_share,
            reason=f"evidence-only:{first.provider}:{first.providerLabel}",
        )
        open_drafts.append(base)
        cluster.base = base
    else:
        base.add_label(fused_label, fused_share)
        base.kind = kind_for_label(fused_label)
    for candidate in cluster.candidates:
        base.cover(candidate.rect)
        base.evidence_ids.append(candidate.evidenceId)
        base.match_notes.append(
            f"evidence:{candidate.provider}:structured:{candidate.providerLabel}"
        )
    return base.rect


def _best_draft_match(
    matches: list[tuple[RegionDraft, MatchResult]],
) -> tuple[RegionDraft, MatchResult]:
    best_index = max(
        range(len(matches)),
        key=lambda index: (matches[index][1].score, -index),
    )
    return matches[best_index]


def _cluster_unmatched(candidates: list[NormalizedCandidate]) -> list[list[NormalizedCandidate]]:
    groups: list[list[NormalizedCandidate]] = []
    for candidate in candidates:
        host: list[NormalizedCandidate] | None = None
        for group in groups:
            if any(_candidates_overlap(candidate, other) for other in group):
                host = group
                break
        if host is None:
            groups.append([candidate])
        else:
            host.append(candidate)
    return groups


def _evidence_only_draft(
    group: list[NormalizedCandidate],
    *,
    registry: Registry | None,
) -> RegionDraft:
    fused_label, fused_share = fuse_candidate_labels(group, registry=registry)
    first = group[0]
    draft = draft_region(
        region_id="pending",
        page_id=first.pageId,
        rect=first.rect,
        label=fused_label,
        confidence=fused_share,
        reason=f"evidence-only:{first.provider}:{first.providerLabel}",
    )
    for candidate in group:
        draft.cover(candidate.rect)
        draft.evidence_ids.append(candidate.evidenceId)
        if candidate is not first:
            draft.match_notes.append(
                f"evidence-only:{candidate.provider}:{candidate.providerLabel}"
            )
    return draft


def fuse_page(
    *,
    drafts: list[RegionDraft],
    candidates: list[NormalizedCandidate],
    region_id_fn: Callable[[int], str],
    registry: Registry | None = None,
) -> list[InternalRegion]:
    """Fuse one page's geometric drafts with normalized provider candidates.

    Candidates that describe the same region are clustered first, then a
    single authority-weighted vote decides the label. Structured
    candidates (TABLE/FORMULA) absorb the text blocks they cover; remaining
    text candidates fold into their best matching block; unmatched
    evidence becomes its own region. Final ids are assigned in page
    reading order so repeated runs are byte-identical.
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
    structured_clusters: list[_CandidateCluster] = []

    for candidate in ordered:
        if candidate.label not in _STRUCTURED_LABELS:
            continue
        matches = _matching_drafts(candidate, open_drafts, ignore_label=True)
        cluster = _find_cluster(candidate, matches, structured_clusters)
        if cluster is None:
            structured_clusters.append(_new_structured_cluster(candidate, matches, open_drafts))
        else:
            _attach_structured(candidate, matches, cluster, open_drafts)

    structured_rects = [
        _apply_structured_cluster(cluster, open_drafts, registry=registry)
        for cluster in structured_clusters
    ]
    consumed = {
        candidate.evidenceId for cluster in structured_clusters for candidate in cluster.candidates
    }

    text_matches: dict[int, list[tuple[NormalizedCandidate, MatchResult]]] = {}
    unmatched: list[NormalizedCandidate] = []
    for candidate in ordered:
        if candidate.evidenceId in consumed:
            continue
        if any(containment(rect, candidate.rect) >= MATCH_CONTAINMENT for rect in structured_rects):
            continue
        matches = _matching_drafts(candidate, open_drafts, ignore_label=False)
        if matches:
            best_draft, best_match = _best_draft_match(matches)
            text_matches.setdefault(id(best_draft), []).append((candidate, best_match))
        else:
            unmatched.append(candidate)

    for draft in open_drafts:
        clustered = text_matches.get(id(draft))
        if clustered:
            fuse_matched_candidates(draft, clustered, registry=registry)

    open_drafts.extend(
        _evidence_only_draft(group, registry=registry) for group in _cluster_unmatched(unmatched)
    )

    open_drafts.sort(key=lambda draft: (draft.rect.y, draft.rect.x, _draft_text(draft)))
    return [
        finalize_draft(draft, region_id_fn(ordinal)) for ordinal, draft in enumerate(open_drafts)
    ]


__all__ = [
    "InternalRegion",
    "MatchResult",
    "RegionLine",
    "authority_weight",
    "capability_for_label",
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
