"""Phase 3.7 caption association + Phase 3.8 footnote recovery tests."""

from __future__ import annotations

from document_model.generated import schema_models as generated
from pdf_pipeline.captions import associate_captions, caption_kind
from pdf_pipeline.footnotes import detect_footnote_ids
from pdf_pipeline.fusion import InternalRegion, RegionLine

NEXT_ID = iter(range(10000))


def _region(
    *,
    text: str,
    x: float,
    y: float,
    width: float,
    height: float,
    kind: generated.LayoutRegionKind = "TEXT",
    label: generated.LayoutLabel = "PARAGRAPH_LIKE",
    font_size: float = 10.0,
) -> InternalRegion:
    region_id = f"r{next(NEXT_ID)}"
    return InternalRegion(
        region_id=region_id,
        page_id="page",
        rect=generated.Rect(kind="rect", x=x, y=y, width=width, height=height),
        kind=kind,
        labels=[generated.LayoutLabelCandidate(label=label, confidence=0.8, evidenceIds=[])],
        confidence=generated.LayoutConfidence(score=0.8, reason="test"),
        lines=[
            RegionLine(
                text=text,
                rect=generated.Rect(kind="rect", x=x, y=y, width=width, height=10),
                font_size=font_size,
            )
        ],
    )


def test_caption_kind_prefixes() -> None:
    assert caption_kind("Figure 1: A diagram") == "FIGURE"
    assert caption_kind("Fig. 2: Another") == "FIGURE"
    assert caption_kind("Table 3: Results") == "TABLE"
    assert caption_kind("Plain paragraph text") is None


def test_figure_caption_below_figure() -> None:
    figure = _region(text="", x=100, y=100, width=200, height=150, kind="FIGURE", label="FIGURE")
    caption = _region(
        text="Figure 1: A diagram",
        x=100,
        y=260,
        width=210,
        height=12,
        label="CAPTION_LIKE",
    )
    associations = associate_captions([figure, caption])
    assert len(associations) == 1
    assert associations[0].main_region_id == figure.region_id
    assert associations[0].caption_region_id == caption.region_id
    assert associations[0].group_kind == "FIGURE_BLOCK"


def test_table_caption_above_table() -> None:
    caption = _region(text="Table 1: Results", x=80, y=100, width=200, height=12)
    table = _region(text="", x=80, y=120, width=210, height=100, kind="TABLE", label="TABLE")
    associations = associate_captions([table, caption])
    assert len(associations) == 1
    assert associations[0].main_region_id == table.region_id
    assert associations[0].group_kind == "TABLE_BLOCK"


def test_too_distant_caption_not_associated() -> None:
    figure = _region(text="", x=100, y=100, width=200, height=150, kind="FIGURE", label="FIGURE")
    caption = _region(text="Figure 1: far away", x=100, y=500, width=210, height=12)
    assert associate_captions([figure, caption]) == []


def test_greedy_assignment_prefers_best_pair() -> None:
    figure_a = _region(text="", x=100, y=100, width=200, height=150, kind="FIGURE", label="FIGURE")
    figure_b = _region(text="", x=100, y=400, width=200, height=150, kind="FIGURE", label="FIGURE")
    caption_a = _region(text="Figure 1: near A", x=100, y=255, width=200, height=12)
    caption_b = _region(text="Figure 2: near B", x=100, y=555, width=200, height=12)
    associations = associate_captions([figure_a, figure_b, caption_a, caption_b])
    assert len(associations) == 2
    pairs = {(a.main_region_id, a.caption_region_id) for a in associations}
    assert (figure_a.region_id, caption_a.region_id) in pairs
    assert (figure_b.region_id, caption_b.region_id) in pairs


def test_footnote_detection_requires_zone_font_and_marker() -> None:
    body = _region(text="Body text without marker.", x=70, y=400, width=210, height=100)
    footnote = _region(
        text="1 Synthetic footnote for layout tests.",
        x=70,
        y=700,
        width=210,
        height=20,
        font_size=8.0,
    )
    small_body = _region(
        text="Small font but no marker at page bottom.",
        x=70,
        y=730,
        width=210,
        height=12,
        font_size=8.0,
    )
    big_marker = _region(
        text="2 Large font footnote.", x=70, y=750, width=210, height=20, font_size=12.0
    )
    ids = detect_footnote_ids(
        [body, footnote, small_body, big_marker], page_height=800, body_font=10.0
    )
    assert footnote.region_id in ids
    assert body.region_id not in ids
    assert small_body.region_id in ids  # wrapped footnote below the marker
    assert big_marker.region_id not in ids  # body-size font is not a footnote


def test_no_footnotes_outside_bottom_zone() -> None:
    note_like = _region(text="1 Not a footnote.", x=70, y=100, width=210, height=20, font_size=8.0)
    ids = detect_footnote_ids([note_like], page_height=800, body_font=10.0)
    assert ids == []
