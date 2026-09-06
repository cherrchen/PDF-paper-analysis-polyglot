"""Phase 3.8 footnote recovery: FootnoteRegion, footnote flow, references.

Footnote regions are page-bottom small-font text blocks that start with a
footnote marker (number or symbol). They form their own per-page flow with
FOOTNOTE_FLOW edges and never enter the primary reading flow, so the main
reading order stays clean (Roadmap M3 Phase 3.8).

Reference evidence (superscript markers in the body) is recovered in
semantic recovery (M4); layout only guarantees the footnote regions
themselves are recovered and separated.
"""

from __future__ import annotations

import re

from pdf_pipeline.fusion import InternalRegion, dominant_label
from pdf_pipeline.geometry import overlap_ratio

# A region in the bottom zone starting with a marker is a footnote.
FOOTNOTE_ZONE_RATIO = 0.72
FOOTNOTE_FONT_FACTOR = 0.95
FOOTNOTE_MARKER = re.compile(r"^(\d{1,2}[.\s]|[*†‡§¶]\s?)")

# Follow-up blocks of a multi-paragraph footnote: attached below a
# footnote without a marker of their own.
_FOOTNOTE_WRAP_GAP_FACTOR = 2.0
_FOOTNOTE_WRAP_X_OVERLAP = 0.5


def is_footnote_candidate(region: InternalRegion, page_height: float, body_font: float) -> bool:
    """Marker-led small-font text block in the bottom page zone."""
    if region.kind != "TEXT" or dominant_label(region) in {"HEADING_LIKE", "CAPTION_LIKE"}:
        return False
    if page_height <= 0 or region.rect.y < FOOTNOTE_ZONE_RATIO * page_height:
        return False
    if body_font > 0 and region.font_size > FOOTNOTE_FONT_FACTOR * body_font:
        return False
    return bool(FOOTNOTE_MARKER.match(region.text.strip()))


def detect_footnote_ids(
    regions: list[InternalRegion],
    *,
    page_height: float,
    body_font: float,
) -> list[str]:
    """Region ids of the page's footnotes in reading order (top to bottom).

    Marker-led candidates seed the set; unmarked small-font blocks directly
    below a footnote (wrapped footnotes) join the same flow.
    """
    candidates = [
        region for region in regions if is_footnote_candidate(region, page_height, body_font)
    ]
    footnote_ids = [region.region_id for region in candidates]
    if not candidates:
        return footnote_ids

    text_regions = [
        region
        for region in regions
        if region.kind == "TEXT"
        and dominant_label(region) not in {"HEADING_LIKE", "CAPTION_LIKE"}
        and region.region_id not in set(footnote_ids)
    ]
    ordered = sorted(candidates, key=lambda region: (region.rect.y, region.rect.x))
    for region in text_regions:
        if page_height <= 0 or region.rect.y < FOOTNOTE_ZONE_RATIO * page_height:
            continue
        if body_font > 0 and region.font_size > FOOTNOTE_FONT_FACTOR * body_font:
            continue
        for footnote in ordered:
            gap = region.rect.y - (footnote.rect.y + footnote.rect.height)
            max_gap = _FOOTNOTE_WRAP_GAP_FACTOR * max(region.font_size, footnote.font_size, 1.0)
            if (
                0 <= gap <= max_gap
                and overlap_ratio(footnote.rect, region.rect) >= _FOOTNOTE_WRAP_X_OVERLAP
            ):
                footnote_ids.append(region.region_id)
                ordered.append(region)
                ordered.sort(key=lambda item: (item.rect.y, item.rect.x))
                break
    return footnote_ids
