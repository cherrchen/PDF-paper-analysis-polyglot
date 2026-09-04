"""Phase 2.2 minimal layout recovery: PhysicalDocument -> LayoutDocument.

Walking Skeleton scope: TextRegion (TEXT), Heading-like regions
(HEADING_LIKE label), and Figure regions (IMAGE/FIGURE), with a simple
band/column split and a linear reading flow graph. No complex fusion; no
MinerU required (evidence adapters arrive in M3).
"""

from __future__ import annotations

from itertools import pairwise

from document_model.generated import schema_models as generated

from pdf_pipeline.ids import stable_uuid
from pdf_pipeline.physical import PRODUCER_VERSION

LAYOUT_PRODUCER = "pdf-pipeline.layout"
LAYOUT_PRODUCER_VERSION = PRODUCER_VERSION

# Heading-like heuristics (deliberately naive; quality is an M3+ concern).
HEADING_MIN_FONT_RATIO = 1.15
HEADING_MAX_SPAN_COUNT = 2
HEADING_MAX_TEXT_LEN = 120

# Column split: both half-page sides must hold a meaningful share of spans
# and the vertical gutter between them must be at least this (relative to
# page width). Real two-column gutters are narrow (~3% of page width).
COLUMN_GAP_RATIO = 0.02
COLUMN_MIN_SIDE_RATIO = 0.25

CONFIDENCE_HEADING = 0.6
CONFIDENCE_TEXT = 0.8
CONFIDENCE_FIGURE = 0.7
CONFIDENCE_COLUMNS = 0.5


def _font_size(span: generated.TextSpan) -> float:
    if span.fontSize is not None:
        return span.fontSize
    return span.geometry.height


def _median_font_size(objects: list[generated.TextSpan]) -> float:
    sizes = sorted(_font_size(span) for span in objects)
    if not sizes:
        return 0.0
    middle = len(sizes) // 2
    if len(sizes) % 2:
        return sizes[middle]
    return (sizes[middle - 1] + sizes[middle]) / 2


def _is_heading_like(span: generated.TextSpan, body_font: float) -> bool:
    if body_font <= 0:
        return False
    font_ratio = _font_size(span) / body_font
    return font_ratio >= HEADING_MIN_FONT_RATIO and len(span.text) <= HEADING_MAX_TEXT_LEN


def _union_rect(
    rects: list[generated.Rect],
) -> generated.Rect:
    x0 = min(r.x for r in rects)
    y0 = min(r.y for r in rects)
    x1 = max(r.x + r.width for r in rects)
    y1 = max(r.y + r.height for r in rects)
    return generated.Rect(kind="rect", x=x0, y=y0, width=x1 - x0, height=y1 - y0)


def _layout_confidence(score: float, reason: str) -> generated.LayoutConfidence:
    return generated.LayoutConfidence(score=score, reason=reason)


def split_columns(spans: list[generated.TextSpan], page_width: float) -> tuple[bool, float]:
    """Return (is_two_column, split_x).

    Naive detection: a real two-column page has a gutter (vertical whitespace
    band) between the right edge of left-column text and the left edge of
    right-column text. Spans crossing the page midpoint (titles, spanning
    captions) are excluded from the gutter measurement; if enough fully
    one-sided spans exist on both sides, the page is two-column.
    """
    if page_width <= 0 or len(spans) < 6:
        return False, page_width / 2
    mid = page_width / 2
    left = [s for s in spans if s.geometry.x + s.geometry.width <= mid]
    right = [s for s in spans if s.geometry.x >= mid]
    min_side = len(spans) * COLUMN_MIN_SIDE_RATIO
    if len(left) < min_side or len(right) < min_side:
        return False, mid
    left_max = max(s.geometry.x + s.geometry.width for s in left)
    right_min = min(s.geometry.x for s in right)
    gap = right_min - left_max
    two_column = gap > 0 and gap / page_width >= COLUMN_GAP_RATIO
    return two_column, (left_max + right_min) / 2 if two_column else mid


def recover_layout_document(physical: generated.PhysicalDocument) -> generated.LayoutDocument:
    """Build a minimal LayoutDocument from a PhysicalDocument.

    One band per page (M2 has no band segmentation), columns split by a
    naive middle-gap test, and three region kinds: TEXT, FIGURE (image
    clusters), with HEADING_LIKE labels on large-font text regions.
    Reading flow is a linear graph over regions in band/column order.
    """
    regions: list[generated.LayoutRegion] = []
    bands: list[generated.PageBand] = []
    columns: list[generated.Column] = []
    pages: list[generated.LayoutPage] = []
    reading_nodes: list[str] = []
    reading_edges: list[generated.ReadingEdge] = []

    page_spans: dict[str, list[generated.TextSpan]] = {}
    page_images: dict[str, list[generated.ImageObject]] = {}
    for obj in physical.objects:
        if obj.objectType == "textSpan":
            page_spans.setdefault(obj.pageId, []).append(obj)
        elif obj.objectType == "imageObject":
            page_images.setdefault(obj.pageId, []).append(obj)

    for page in physical.pages:
        spans = page_spans.get(page.id, [])
        images = page_images.get(page.id, [])
        body_font = _median_font_size(spans)

        band_id = stable_uuid(physical.sourceFingerprint or physical.id, "band", page.index)
        two_column, split_x = split_columns(spans, page.geometry.widthPt)
        layout_mode = "MULTI_COLUMN" if two_column else "SINGLE_COLUMN"

        page_region_ids: list[str] = []
        band_column_ids: list[str] = []

        # Figure regions from image objects (one region per image; clustering
        # is an M3+ concern).
        for image in images:
            region_id = stable_uuid(
                physical.sourceFingerprint or physical.id, "fig", page.index, len(regions)
            )
            regions.append(
                generated.LayoutRegion(
                    id=region_id,
                    pageId=page.id,
                    geometry=image.geometry,
                    kind="FIGURE",
                    childIds=[],
                    physicalObjectIds=[image.id],
                    labels=[
                        generated.LayoutLabelCandidate(
                            label="FIGURE",
                            confidence=CONFIDENCE_FIGURE,
                            evidenceIds=[],
                        )
                    ],
                    confidence=_layout_confidence(CONFIDENCE_FIGURE, "image object"),
                    provenanceIds=[],
                )
            )
            page_region_ids.append(region_id)

        # Text regions: one region per text span, labeled heading-like when
        # the font-size heuristic fires.
        column_spans: dict[str, list[str]] = {"left": [], "right": []}
        for span in spans:
            is_heading = _is_heading_like(span, body_font)
            region_id = stable_uuid(
                physical.sourceFingerprint or physical.id, "txt", page.index, len(regions)
            )
            regions.append(
                generated.LayoutRegion(
                    id=region_id,
                    pageId=page.id,
                    geometry=span.geometry,
                    kind="TEXT",
                    childIds=[],
                    physicalObjectIds=[span.id],
                    labels=[
                        generated.LayoutLabelCandidate(
                            label="HEADING_LIKE" if is_heading else "PARAGRAPH_LIKE",
                            confidence=(CONFIDENCE_HEADING if is_heading else CONFIDENCE_TEXT),
                            evidenceIds=[],
                        )
                    ],
                    confidence=_layout_confidence(
                        CONFIDENCE_HEADING if is_heading else CONFIDENCE_TEXT,
                        "font-size heuristic" if is_heading else "text span",
                    ),
                    provenanceIds=[],
                )
            )
            page_region_ids.append(region_id)
            side = "right" if two_column and span.geometry.x >= split_x else "left"
            column_spans[side].append(region_id)

        # Columns hold their regions in reading order.
        if two_column:
            for side, index in (("left", 0), ("right", 1)):
                column_id = stable_uuid(
                    physical.sourceFingerprint or physical.id, "col", page.index, index
                )
                band_column_ids.append(column_id)
                members = column_spans[side]
                columns.append(
                    generated.Column(
                        id=column_id,
                        pageId=page.id,
                        bandId=band_id,
                        geometry=generated.Rect(
                            kind="rect",
                            x=0.0 if side == "left" else split_x,
                            y=0.0,
                            width=split_x if side == "left" else page.geometry.widthPt - split_x,
                            height=page.geometry.heightPt,
                        ),
                        regionIds=members,
                    )
                )
            ordered_ids = column_spans["left"] + column_spans["right"]
        else:
            column_id = stable_uuid(physical.sourceFingerprint or physical.id, "col", page.index, 0)
            band_column_ids.append(column_id)
            columns.append(
                generated.Column(
                    id=column_id,
                    pageId=page.id,
                    bandId=band_id,
                    geometry=generated.Rect(
                        kind="rect",
                        x=0.0,
                        y=0.0,
                        width=page.geometry.widthPt,
                        height=page.geometry.heightPt,
                    ),
                    regionIds=page_region_ids,
                )
            )
            ordered_ids = page_region_ids

        bands.append(
            generated.PageBand(
                id=band_id,
                pageId=page.id,
                yStart=0.0,
                yEnd=page.geometry.heightPt,
                layoutMode=layout_mode,
                columnIds=band_column_ids,
            )
        )
        pages.append(
            generated.LayoutPage(pageId=page.id, regionIds=page_region_ids, bandIds=[band_id])
        )
        reading_nodes.extend(ordered_ids)

    # Linear reading flow across the whole document.
    for source, target in pairwise(reading_nodes):
        reading_edges.append(
            generated.ReadingEdge(
                source=source,
                target=target,
                confidence=CONFIDENCE_COLUMNS,
                reason="SAME_COLUMN",
            )
        )

    return generated.LayoutDocument(
        schemaVersion="0.1.0",
        id=stable_uuid(physical.sourceFingerprint or physical.id, "layout-document"),
        physicalDocumentId=physical.id,
        pages=pages,
        regions=regions,
        bands=bands,
        columns=columns,
        groups=[],
        readingFlow=generated.ReadingFlowGraph(nodes=reading_nodes, edges=reading_edges),
        primaryFlow=list(reading_nodes),
    )
