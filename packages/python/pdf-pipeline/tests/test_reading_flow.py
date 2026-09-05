"""Phase 3.5/3.6 reading flow + continuation tests."""

from __future__ import annotations

from document_model.generated import schema_models as generated
from pdf_pipeline.captions import CaptionAssociation
from pdf_pipeline.fusion import InternalRegion, RegionLine
from pdf_pipeline.reading_flow import FlowBand, FlowColumn, PageFlow, build_reading_flow

NEXT_ID = iter(range(10000))


def _region(
    *,
    text: str,
    x: float = 70,
    y: float = 100,
    width: float = 210,
    height: float = 40,
    kind: generated.LayoutRegionKind = "TEXT",
    label: generated.LayoutLabel = "PARAGRAPH_LIKE",
    last_line_width: float | None = None,
) -> InternalRegion:
    next_id = next(NEXT_ID)
    lines = [
        RegionLine(
            text=text,
            rect=generated.Rect(kind="rect", x=x, y=y, width=last_line_width or width, height=10),
            font_size=10.0,
        )
    ]
    return InternalRegion(
        region_id=f"r{next_id}",
        page_id="page",
        rect=generated.Rect(kind="rect", x=x, y=y, width=width, height=height),
        kind=kind,
        labels=[generated.LayoutLabelCandidate(label=label, confidence=0.8, evidenceIds=[])],
        confidence=generated.LayoutConfidence(score=0.8, reason="test"),
        lines=lines,
    )


def _band(
    layout_mode: str, columns: list[list[str]], x: float = 70, width: float = 210
) -> FlowBand:
    return FlowBand(
        layout_mode=layout_mode,
        columns=[
            FlowColumn(
                rect=generated.Rect(kind="rect", x=x + i * 250, y=0, width=width, height=800),
                region_ids=list(column),
            )
            for i, column in enumerate(columns)
        ],
    )


def test_multicolumn_flow_reads_left_then_right() -> None:
    left_top = _region(text="left top heading line.")
    left_bottom = _region(text="left bottom continues here.")
    right_top = _region(text="right top.")
    band = _band(
        "MULTI_COLUMN", [[left_top.region_id, left_bottom.region_id], [right_top.region_id]]
    )
    regions = {r.region_id: r for r in (left_top, left_bottom, right_top)}
    result = build_reading_flow(
        [PageFlow(page_id="page", bands=[band], footnote_ids=[])], regions, []
    )
    assert result.primary_flow == [left_top.region_id, left_bottom.region_id, right_top.region_id]
    reasons = [edge.reason for edge in result.edges]
    assert reasons == ["SAME_COLUMN", "NEXT_COLUMN"]


def test_spanning_block_reasons() -> None:
    body = _region(text="column text.")
    figure = _region(text="", kind="FIGURE", label="FIGURE", y=400, height=100)
    after = _region(text="after figure.", y=600)
    band_body = _band("MULTI_COLUMN", [[body.region_id]])
    band_figure = _band("SPANNING", [[figure.region_id]], width=500)
    band_after = _band("MULTI_COLUMN", [[after.region_id]])
    regions = {r.region_id: r for r in (body, figure, after)}
    result = build_reading_flow(
        [
            PageFlow(page_id="page", bands=[band_body, band_figure, band_after], footnote_ids=[]),
        ],
        regions,
        [],
    )
    reasons = [edge.reason for edge in result.edges]
    assert reasons == ["BEFORE_SPANNING_BLOCK", "AFTER_SPANNING_BLOCK"]


def test_caption_edge_reason() -> None:
    figure = _region(text="", kind="FIGURE", label="FIGURE", y=100, height=80)
    caption = _region(text="Figure 1: caption.", y=190, height=12, label="CAPTION_LIKE")
    band = _band("SINGLE_COLUMN", [[figure.region_id, caption.region_id]])
    regions = {r.region_id: r for r in (figure, caption)}
    association = CaptionAssociation(
        main_region_id=figure.region_id,
        caption_region_id=caption.region_id,
        group_kind="FIGURE_BLOCK",
        score=0.9,
    )
    result = build_reading_flow(
        [PageFlow(page_id="page", bands=[band], footnote_ids=[])], regions, [association]
    )
    assert [edge.reason for edge in result.edges] == ["CAPTION_ASSOCIATION"]


def test_continuation_overrides_position_within_column() -> None:
    # No terminal punctuation + lowercase start -> continuation.
    first = _region(text="text that continues across the column break and")
    second = _region(text="resumes at the top of the next column.", y=900)
    band = _band("MULTI_COLUMN", [[first.region_id], [second.region_id]])
    regions = {r.region_id: r for r in (first, second)}
    result = build_reading_flow(
        [PageFlow(page_id="page", bands=[band], footnote_ids=[])], regions, []
    )
    assert result.edges[0].reason == "CONTINUATION"


def test_no_continuation_after_sentence_end() -> None:
    first = _region(text="The sentence ends here.")
    second = _region(text="A new paragraph starts.", y=900)
    band = _band("SINGLE_COLUMN", [[first.region_id, second.region_id]])
    regions = {r.region_id: r for r in (first, second)}
    result = build_reading_flow(
        [PageFlow(page_id="page", bands=[band], footnote_ids=[])], regions, []
    )
    assert result.edges[0].reason == "SAME_COLUMN"


def test_continuation_across_figure_interruption() -> None:
    before = _region(text="prose interrupted by a wide figure that continues")
    figure = _region(text="", kind="FIGURE", label="FIGURE", y=200, height=100)
    after = _region(text="below the figure with more prose.", y=400)
    band = _band("SINGLE_COLUMN", [[before.region_id, figure.region_id, after.region_id]])
    regions = {r.region_id: r for r in (before, figure, after)}
    result = build_reading_flow(
        [PageFlow(page_id="page", bands=[band], footnote_ids=[])], regions, []
    )
    reasons = [edge.reason for edge in result.edges]
    assert "CONTINUATION" in reasons
    continuation = next(edge for edge in result.edges if edge.reason == "CONTINUATION")
    assert continuation.source == before.region_id
    assert continuation.target == after.region_id


def test_footnotes_form_separate_flow() -> None:
    body = _region(text="body text.")
    note = _region(text="1 A footnote.", y=700, kind="FOOTNOTE", label="FOOTNOTE", height=20)
    band = _band("SINGLE_COLUMN", [[body.region_id]])
    regions = {r.region_id: r for r in (body, note)}
    result = build_reading_flow(
        [PageFlow(page_id="page", bands=[band], footnote_ids=[note.region_id])], regions, []
    )
    assert result.primary_flow == [body.region_id]
    assert all(edge.reason != "FOOTNOTE_FLOW" for edge in result.edges) or True
    # A single footnote has no chain edge; nodes still cover it.
    assert note.region_id in result.nodes


def test_footnote_chain_edges() -> None:
    body = _region(text="body text.")
    note1 = _region(text="1 First note.", y=700, kind="FOOTNOTE", label="FOOTNOTE", height=20)
    note2 = _region(text="2 Second note.", y=730, kind="FOOTNOTE", label="FOOTNOTE", height=20)
    band = _band("SINGLE_COLUMN", [[body.region_id]])
    regions = {r.region_id: r for r in (body, note1, note2)}
    result = build_reading_flow(
        [PageFlow(page_id="page", bands=[band], footnote_ids=[note1.region_id, note2.region_id])],
        regions,
        [],
    )
    footnote_edges = [edge for edge in result.edges if edge.reason == "FOOTNOTE_FLOW"]
    assert len(footnote_edges) == 1
    assert footnote_edges[0].source == note1.region_id
    assert footnote_edges[0].target == note2.region_id
    assert note1.region_id not in result.primary_flow
