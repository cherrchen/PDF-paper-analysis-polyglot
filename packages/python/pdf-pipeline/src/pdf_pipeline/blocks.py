"""Per-column text blocking on structural items (M3 baseline).

Blocking runs AFTER band/column detection (see
:mod:`pdf_pipeline.page_structure`) so full-width lines cannot bridge the
two columns of a paragraph block: each column's items are blocked
independently.

Baseline heuristics deliberately stop short of paragraph segmentation:
layout regions are visual runs; paragraph identity is semantic recovery's
decision (M4) guided by continuation evidence (Phase 3.6).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pdf_pipeline.furniture import font_size
from pdf_pipeline.fusion import RegionLine, draft_region
from pdf_pipeline.geometry import as_rect, overlap_ratio, union_rect, vertical_gap
from pdf_pipeline.ids import stable_uuid

if TYPE_CHECKING:
    from document_model.generated import schema_models as generated

    from pdf_pipeline.fusion import RegionDraft
    from pdf_pipeline.page_structure import PageItem

# Line clustering into text blocks.
BLOCK_LINE_GAP_FACTOR = 0.75
BLOCK_MIN_GAP_PT = 4.0
BLOCK_MIN_X_OVERLAP = 0.4
# A line starting this far right of its block's left edge begins a new
# block (LaTeX \parindent is ~1.5em; centered lines also exceed this).
BLOCK_INDENT_FACTOR = 1.2

# Clusters thinner than this are decoration (booktabs rules, separators).
MIN_GRAPHIC_THICKNESS_PT = 2.0


def build_text_block_drafts(
    *,
    page_id: str,
    fingerprint: str,
    page_index: int,
    column_tag: tuple[int, int],
    items: list[PageItem],
    body_font: float,
    start_ordinal: int,
) -> list[RegionDraft]:
    """Cluster a column's text lines into block drafts.

    Lines are consumed in reading order (y, then x). A line joins the
    compatible open block with the smallest vertical gap: enough horizontal
    overlap, small enough gap, and not paragraph-indented relative to the
    block's left edge.
    """
    spans = [
        item.span
        for item in sorted(items, key=lambda item: (item.rect.y, item.rect.x))
        if item.span
    ]
    blocks: list[list[generated.TextSpan]] = []
    indent_threshold = BLOCK_INDENT_FACTOR * body_font if body_font > 0 else 0.0
    max_gap = (
        max(BLOCK_MIN_GAP_PT, BLOCK_LINE_GAP_FACTOR * body_font)
        if body_font > 0
        else BLOCK_MIN_GAP_PT
    )
    for span in spans:
        rect = as_rect(span.geometry)
        height = rect.height or 1.0
        best: list[generated.TextSpan] | None = None
        best_gap = float("inf")
        for block in blocks:
            block_rect = _span_block_rect(block)
            if overlap_ratio(block_rect, rect) < BLOCK_MIN_X_OVERLAP:
                continue
            gap = vertical_gap(block_rect, rect)
            if gap > max_gap or rect.y < block_rect.y - height:
                continue
            if indent_threshold > 0 and rect.x >= block_rect.x + indent_threshold:
                # Paragraph indent or centered line: starts a new block.
                continue
            if gap < best_gap:
                best = block
                best_gap = gap
        if best is None:
            blocks.append([span])
        else:
            best.append(span)

    drafts: list[RegionDraft] = []
    for ordinal, block in enumerate(blocks, start=start_ordinal):
        block_rect = _span_block_rect(block)
        lines = [
            RegionLine(
                text=span.text,
                rect=as_rect(span.geometry),
                font_size=font_size(span),
            )
            for span in sorted(
                block, key=lambda obj: (as_rect(obj.geometry).y, as_rect(obj.geometry).x)
            )
        ]
        block_font = max(line.font_size for line in lines)
        label = (
            "HEADING_LIKE" if _is_heading_like(block_font, body_font, lines) else "PARAGRAPH_LIKE"
        )
        confidence = 0.6 if label == "HEADING_LIKE" else 0.75
        drafts.append(
            draft_region(
                region_id=stable_block_id(fingerprint, page_index, ordinal),
                page_id=page_id,
                rect=block_rect,
                label=label,
                confidence=confidence,
                physical_object_ids=[span.id for span in block],
                lines=lines,
                column_tag=column_tag,
                reason=(
                    f"geometric-block:"
                    f"{'font-heuristic' if label == 'HEADING_LIKE' else 'line-cluster'}"
                ),
            )
        )
    return drafts


def _is_heading_like(
    font: float,
    body_font: float,
    lines: list[RegionLine],
) -> bool:
    if body_font <= 0 or font / body_font < 1.15:
        return False
    text = " ".join(line.text for line in lines)
    return len(text) <= 120 and len(lines) <= 2


def stable_block_id(fingerprint: str, page_index: int, ordinal: int) -> str:
    """Stable placeholder id; layout.py re-assigns final ids after fusion."""
    return stable_uuid(fingerprint, "draft", page_index, ordinal)


def _span_block_rect(block: list[generated.TextSpan]) -> generated.Rect:
    rect = as_rect(block[0].geometry)
    for obj in block[1:]:
        rect = union_rect(rect, as_rect(obj.geometry))
    return rect


def build_figure_drafts(
    *,
    page_id: str,
    fingerprint: str,
    page_index: int,
    column_tag: tuple[int, int],
    items: list[PageItem],
    start_ordinal: int,
) -> list[RegionDraft]:
    """Cluster a column's graphic items (images, vector paths) into figures.

    Graphics closer than :data:`GRAPHIC_MERGE_GAP_PT` merge into one
    figure region (TikZ diagrams arrive as many separate paths). Clusters
    thinner than :data:`MIN_GRAPHIC_THICKNESS_PT` in either dimension are
    decoration (booktabs rules, separators) and are dropped.
    """
    drafts: list[RegionDraft] = []
    ordinal = start_ordinal
    for item in sorted(
        (candidate for candidate in items if candidate.is_graphic),
        key=lambda item: (item.rect.y, item.rect.x),
    ):
        if (
            item.rect.height < MIN_GRAPHIC_THICKNESS_PT
            or item.rect.width < MIN_GRAPHIC_THICKNESS_PT
        ):
            continue
        drafts.append(
            draft_region(
                region_id=stable_block_id(fingerprint, page_index, ordinal),
                page_id=page_id,
                rect=item.rect,
                label="FIGURE",
                confidence=0.7,
                physical_object_ids=item.object_ids,
                column_tag=column_tag,
                reason="graphic-cluster",
            )
        )
        ordinal += 1
    return drafts


def build_furniture_drafts(
    *,
    page_id: str,
    fingerprint: str,
    page_index: int,
    headers: list[generated.TextSpan],
    footers: list[generated.TextSpan],
    start_ordinal: int,
) -> list[RegionDraft]:
    """Header/footer drafts: kept out of the main reading flow."""
    drafts: list[RegionDraft] = []
    ordinal = start_ordinal
    for kind, spans in (("HEADER", headers), ("FOOTER", footers)):
        for span in sorted(
            spans, key=lambda obj: (as_rect(obj.geometry).y, as_rect(obj.geometry).x)
        ):
            drafts.append(
                draft_region(
                    region_id=stable_block_id(fingerprint, page_index, ordinal),
                    page_id=page_id,
                    rect=as_rect(span.geometry),
                    label=kind,
                    confidence=0.7,
                    physical_object_ids=[span.id],
                    lines=[
                        RegionLine(
                            text=span.text,
                            rect=as_rect(span.geometry),
                            font_size=font_size(span),
                        )
                    ],
                    reason="page-furniture",
                )
            )
            ordinal += 1
    return drafts


__all__ = [
    "build_figure_drafts",
    "build_furniture_drafts",
    "build_text_block_drafts",
]
