"""Phase 3.2 region fusion tests: matching, weighting, page fusion."""

from __future__ import annotations

from typing import cast

import pytest
from document_model.generated import schema_models as generated
from pdf_pipeline.capabilities import Capability, load_registry
from pdf_pipeline.evidence.normalize import NormalizedCandidate
from pdf_pipeline.fusion import (
    AUTHORITY_WEIGHT_FALLBACK,
    NON_AUTHORITY_WEIGHT,
    RegionDraft,
    authority_weight,
    draft_region,
    fuse_candidate_labels,
    fuse_page,
    label_similarity,
    match_candidate,
    text_overlap_ratio,
)
from pdf_pipeline.geometry import union_rect

FINGERPRINT = "0" * 64


def _candidate(  # noqa: PLR0917 - geometry shorthand mirrors Rect fields
    evidence_id: str,
    x: float,
    y: float,
    width: float,
    height: float,
    label: generated.LayoutLabel = "PARAGRAPH_LIKE",
    confidence: float = 0.6,
    preview: str = "",
    provider: str = "mock",
) -> NormalizedCandidate:
    return NormalizedCandidate(
        evidenceId=evidence_id,
        pageId="page",
        rect=generated.Rect(kind="rect", x=x, y=y, width=width, height=height),
        label=label,
        providerLabel=label.lower(),
        provider=provider,
        confidence=confidence,
        textPreview=preview,
        provenanceIds=(),
    )


def _rect(x: float, y: float, width: float, height: float) -> generated.Rect:
    return generated.Rect(kind="rect", x=x, y=y, width=width, height=height)


def test_label_similarity_matrix() -> None:
    assert label_similarity("TEXT", "TEXT") == 1.0
    assert label_similarity("TEXT", "PARAGRAPH_LIKE") == 0.9
    assert label_similarity("PARAGRAPH_LIKE", "TEXT") == 0.9  # symmetric
    assert label_similarity("PARAGRAPH_LIKE", "TABLE") == 0.0


def test_text_overlap_ratio() -> None:
    assert text_overlap_ratio("the cat sat", "the cat sat on the mat") == 1.0
    assert text_overlap_ratio("alpha beta", "gamma delta") == 0.0
    assert text_overlap_ratio("", "anything") == 0.0


def test_match_candidate_requires_geometry_and_label() -> None:
    candidate = _candidate("e1", 0, 0, 100, 50, label="PARAGRAPH_LIKE", preview="hello world")
    match = match_candidate(candidate, rect=_rect(2, 1, 98, 49), label="PARAGRAPH_LIKE")
    assert match is not None
    assert match.score > 0

    # No geometry agreement -> no match.
    assert match_candidate(candidate, rect=_rect(500, 500, 10, 10), label="PARAGRAPH_LIKE") is None
    # Incompatible labels -> no match even on identical geometry.
    table = _candidate("e2", 0, 0, 100, 50, label="TABLE")
    assert match_candidate(table, rect=_rect(0, 0, 100, 50), label="PARAGRAPH_LIKE") is None
    # Structured matching may ignore labels.
    assert (
        match_candidate(table, rect=_rect(0, 0, 100, 50), label="PARAGRAPH_LIKE", ignore_label=True)
        is not None
    )


def test_match_candidate_records_match_key() -> None:
    candidate = _candidate("e1", 0, 0, 100, 50, label="PARAGRAPH_LIKE")
    match = match_candidate(candidate, rect=_rect(0, 0, 100, 50), label="PARAGRAPH_LIKE")
    assert match is not None
    assert "match_key" in match.via
    assert candidate.match_key()[0] == "page"


def test_fuse_page_folds_matching_candidates_into_blocks() -> None:
    draft = draft_region(
        region_id="d1",
        page_id="page",
        rect=_rect(10, 10, 100, 40),
        label="PARAGRAPH_LIKE",
        confidence=0.75,
        reason="geometric-block:line-cluster",
    )
    candidate = _candidate("ev1", 12, 12, 96, 36, preview="some text", confidence=0.8)
    regions = fuse_page(drafts=[draft], candidates=[candidate], region_id_fn=lambda i: f"r{i}")
    assert len(regions) == 1
    region = regions[0]
    assert region.evidence_ids == ["ev1"]
    assert region.confidence.reason is not None
    assert "evidence:mock:" in region.confidence.reason


def test_fuse_page_structured_candidate_absorbs_blocks() -> None:
    rows = [_rect(20, 10, 160, 12), _rect(20, 30, 160, 12), _rect(20, 50, 160, 12)]
    drafts = [
        draft_region(
            region_id=f"d{i}",
            page_id="page",
            rect=rect,
            label="PARAGRAPH_LIKE",
            confidence=0.75,
            reason="geometric-block:line-cluster",
        )
        for i, rect in enumerate(rows)
    ]
    table = _candidate("tab1", 20, 10, 160, 52, label="TABLE", confidence=0.6)
    regions = fuse_page(drafts=drafts, candidates=[table], region_id_fn=lambda i: f"r{i}")
    assert len(regions) == 1
    assert regions[0].kind == "TABLE"
    assert regions[0].rect.height >= 52


def test_fuse_page_unmatched_candidate_becomes_region() -> None:
    candidate = _candidate("evX", 300, 400, 50, 20, label="FIGURE", confidence=0.7)
    regions = fuse_page(drafts=[], candidates=[candidate], region_id_fn=lambda i: f"r{i}")
    assert len(regions) == 1
    assert regions[0].kind == "FIGURE"
    assert regions[0].evidence_ids == ["evX"]


def test_fuse_page_drops_cell_noise_inside_structured_region() -> None:
    table = _candidate("tab1", 0, 0, 100, 100, label="TABLE", confidence=0.6)
    cell_noise = _candidate("cell1", 5, 5, 40, 10, label="PARAGRAPH_LIKE", confidence=0.9)
    regions = fuse_page(drafts=[], candidates=[table, cell_noise], region_id_fn=lambda i: f"r{i}")
    assert len(regions) == 1
    assert regions[0].kind == "TABLE"


def test_fuse_page_is_deterministic() -> None:
    rows = [_rect(20, 10, 160, 12), _rect(20, 30, 160, 12), _rect(20, 50, 160, 12)]
    candidates = [
        _candidate("t1", 20, 10, 160, 52, label="TABLE"),
        _candidate("p1", 20, 10, 160, 12, preview="alpha beta gamma"),
    ]

    def fresh_drafts() -> list[RegionDraft]:
        return [
            draft_region(
                region_id=f"d{i}",
                page_id="page",
                rect=rect,
                label="PARAGRAPH_LIKE",
                confidence=0.75,
                reason="geometric-block",
            )
            for i, rect in enumerate(rows)
        ]

    a = fuse_page(drafts=fresh_drafts(), candidates=candidates, region_id_fn=lambda i: f"r{i}")
    b = fuse_page(drafts=fresh_drafts(), candidates=candidates, region_id_fn=lambda i: f"r{i}")
    assert a == b


def test_union_rect_covers_both() -> None:
    a = _rect(0, 0, 10, 10)
    b = _rect(5, 5, 10, 10)
    merged = union_rect(a, b)
    assert (merged.x, merged.y, merged.width, merged.height) == (0, 0, 15, 15)


# --- Phase 7.4: capability-authority conflict resolution ------------------


def _vote_candidate(
    label: str,
    confidence: float,
    provider: str,
) -> NormalizedCandidate:
    """A minimal normalized candidate for label-vote tests."""
    return NormalizedCandidate(
        evidenceId=f"ev-{provider}-{label}-{confidence}",
        pageId="p",
        rect=generated.Rect(kind="rect", x=0, y=0, width=10, height=10),
        label=cast("generated.LayoutLabel", label),
        providerLabel=label,
        provider=provider,
        confidence=confidence,
        textPreview="",
        provenanceIds=(),
    )


def test_authority_beats_naive_majority() -> None:
    """Two unlisted providers must not outvote the capability authority."""
    candidates = [
        _vote_candidate("PARAGRAPH_LIKE", 0.5, "unknown-a"),
        _vote_candidate("PARAGRAPH_LIKE", 0.5, "unknown-b"),
        _vote_candidate("HEADING_LIKE", 0.75, "mock"),  # layout.region primary
    ]
    naive = fuse_candidate_labels(candidates)
    assert naive[0] == "PARAGRAPH_LIKE"
    weighted = fuse_candidate_labels(candidates, registry=load_registry())
    assert weighted[0] == "HEADING_LIKE"


def test_challenger_still_counts_against_primary() -> None:
    """Challenger weight keeps cross-source evidence usable, not silenced."""
    candidates = [
        _vote_candidate("HEADING_LIKE", 0.6, "mock"),
        _vote_candidate("PARAGRAPH_LIKE", 0.6, "docling-sim"),  # layout.region challenger
    ]
    label, _ = fuse_candidate_labels(candidates, registry=load_registry())
    assert label == "HEADING_LIKE"  # 0.6 * 1.5 beats 0.6 * 1.2


def test_table_structure_authority_resolves_table_labels() -> None:
    """table.structure fallback outranks unlisted providers at equal confidence."""
    candidates = [
        _vote_candidate("TABLE", 0.6, "mock"),  # table.structure fallback
        _vote_candidate("TEXT", 0.6, "unknown-a"),
    ]
    naive_label, _ = fuse_candidate_labels(candidates)
    assert naive_label == "TEXT"  # alphabetical tie-break without a registry
    label, _ = fuse_candidate_labels(candidates, registry=load_registry())
    assert label == "TABLE"


def test_unlisted_provider_keeps_reduced_voice() -> None:
    """Cross-source evidence is reduced, never silenced (§43)."""
    candidates = [
        _vote_candidate("PARAGRAPH_LIKE", 0.5, "unknown-a"),
        _vote_candidate("CAPTION_LIKE", 0.5, "unknown-b"),
    ]
    label, share = fuse_candidate_labels(candidates, registry=load_registry())
    assert label == "PARAGRAPH_LIKE"
    assert share == pytest.approx(0.5)


def test_authority_weight_uses_named_roles() -> None:
    """Empty slots must not promote fallback to challenger or unlisted to challenger."""
    registry = load_registry()
    assert authority_weight(registry, "TABLE", "mock") == AUTHORITY_WEIGHT_FALLBACK
    assert authority_weight(registry, "FORMULA", "unknown") == NON_AUTHORITY_WEIGHT


def _layout_registry(primary: str, challenger: str) -> dict[str, Capability]:
    overlay = dict(load_registry())
    slot = overlay["layout.region"]
    overlay["layout.region"] = Capability(
        name=slot.name,
        primary=primary,
        challenger=challenger,
        fallback=slot.fallback,
    )
    return overlay


def test_fuse_page_arbitrates_after_aggregating_providers() -> None:
    """Swapping layout.region primary must change which overlapping label wins."""
    draft = draft_region(
        region_id="d1",
        page_id="page",
        rect=_rect(10, 10, 100, 40),
        label="PARAGRAPH_LIKE",
        confidence=0.5,
        reason="geometric-block",
    )
    heading = _candidate(
        "ev-h", 10, 10, 100, 40, label="HEADING_LIKE", confidence=0.6, provider="mock"
    )
    paragraph = _candidate(
        "ev-p", 10, 10, 100, 40, label="PARAGRAPH_LIKE", confidence=0.6, provider="docling-sim"
    )
    mock_primary = fuse_page(
        drafts=[draft],
        candidates=[heading, paragraph],
        region_id_fn=lambda i: f"r{i}",
        registry=_layout_registry("mock", "docling-sim"),
    )
    assert mock_primary[0].labels[0].label == "HEADING_LIKE"

    draft_swapped = draft_region(
        region_id="d1",
        page_id="page",
        rect=_rect(10, 10, 100, 40),
        label="PARAGRAPH_LIKE",
        confidence=0.5,
        reason="geometric-block",
    )
    swapped = fuse_page(
        drafts=[draft_swapped],
        candidates=[heading, paragraph],
        region_id_fn=lambda i: f"r{i}",
        registry=_layout_registry("docling-sim", "mock"),
    )
    assert swapped[0].labels[0].label == "PARAGRAPH_LIKE"


def test_fuse_page_low_confidence_does_not_get_unit_share() -> None:
    """A 0.1 candidate must not receive fused_share 1.0 just because it was alone."""
    draft = draft_region(
        region_id="d1",
        page_id="page",
        rect=_rect(10, 10, 100, 40),
        label="PARAGRAPH_LIKE",
        confidence=0.5,
        reason="geometric-block",
    )
    low = _candidate("ev-low", 10, 10, 100, 40, label="HEADING_LIKE", confidence=0.1)
    high = _candidate("ev-high", 10, 10, 100, 40, label="PARAGRAPH_LIKE", confidence=0.9)
    regions = fuse_page(drafts=[draft], candidates=[low, high], region_id_fn=lambda i: f"r{i}")
    assert regions[0].labels[0].label == "PARAGRAPH_LIKE"
    assert regions[0].labels[0].confidence == pytest.approx(0.9)


def test_fuse_page_structured_authority_beats_confidence() -> None:
    """TABLE/FORMULA clusters vote with authority weights, not a fixed 1.5."""
    draft = draft_region(
        region_id="d1",
        page_id="page",
        rect=_rect(0, 0, 100, 50),
        label="PARAGRAPH_LIKE",
        confidence=0.5,
        reason="geometric-block",
    )
    table = _candidate("ev-t", 0, 0, 100, 50, label="TABLE", confidence=0.5, provider="docling-sim")
    formula = _candidate("ev-f", 0, 0, 100, 50, label="FORMULA", confidence=0.8, provider="unknown")
    default = fuse_page(
        drafts=[draft],
        candidates=[table, formula],
        region_id_fn=lambda i: f"r{i}",
        registry=load_registry(),
    )
    # table.structure primary 0.5*1.5=0.75 beats unlisted formula 0.8*0.8=0.64
    assert default[0].kind == "TABLE"

    overlay = dict(load_registry())
    slot = overlay["formula.detection"]
    overlay["formula.detection"] = Capability(
        name=slot.name, primary="unknown", challenger=slot.challenger, fallback=slot.fallback
    )
    draft_swapped = draft_region(
        region_id="d1",
        page_id="page",
        rect=_rect(0, 0, 100, 50),
        label="PARAGRAPH_LIKE",
        confidence=0.5,
        reason="geometric-block",
    )
    swapped = fuse_page(
        drafts=[draft_swapped],
        candidates=[table, formula],
        region_id_fn=lambda i: f"r{i}",
        registry=overlay,
    )
    # unknown becomes formula.detection primary: 0.8*1.5=1.2 beats 0.75
    assert swapped[0].kind == "FORMULA"
