"""Phase 3.2 region fusion tests: matching, weighting, page fusion."""

from __future__ import annotations

from document_model.generated import schema_models as generated
from pdf_pipeline.evidence.normalize import NormalizedCandidate
from pdf_pipeline.fusion import (
    RegionDraft,
    draft_region,
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
) -> NormalizedCandidate:
    return NormalizedCandidate(
        evidenceId=evidence_id,
        pageId="page",
        rect=generated.Rect(kind="rect", x=x, y=y, width=width, height=height),
        label=label,
        providerLabel=label.lower(),
        provider="mock",
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
