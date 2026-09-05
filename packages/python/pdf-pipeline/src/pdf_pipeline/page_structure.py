"""Phase 3.3 page band detection + Phase 3.4 column recovery (XY-cut).

Page structure is recovered from raw page items (text lines, images) with
a deterministic recursive XY-cut BEFORE text blocking, because full-width
lines (titles, abstracts) would otherwise bridge the two columns of a
paragraph block.

1. Horizontal cuts first: y-gaps that span the full x-extent of the
   current item range split it into strips (title band, body, spanning
   figure band, ...).
2. Within a strip, vertical cuts: x-gaps that span the strip's full
   y-extent split it into columns. A gap inside a single line (equations,
   table cells) does not span the strip height, so it never splits.
3. Each strip becomes one band with its recovered columns; bands are
   classified FULL_WIDTH / SINGLE_COLUMN / MULTI_COLUMN / SPANNING.

Unbalanced columns fall out naturally: the gutter cut keeps each column's
items together even when one column ends higher than the other. The
result supports real paper layouts such as
``Title → 2 columns → wide figure → 2 columns``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from document_model.generated import schema_models as generated

from pdf_pipeline.geometry import as_rect

if TYPE_CHECKING:
    from collections.abc import Iterable

# Horizontal cut: a full-width y-gap of at least this much splits strips
# (display skips are ~12pt, line leading ~3pt).
HORIZONTAL_GAP_PT = 9.0

# Vertical cut: an x-gap of at least this much and spanning the full
# strip height separates columns (LaTeX \columnsep default 10pt).
GUTTER_MIN_RATIO = 0.015
GUTTER_MIN_PT = 7.0
# A real column is at least this wide; narrower x-islands (equation
# numbers, table rules) merge back into their nearest neighbor.
MIN_COLUMN_RATIO = 0.15

# Classification: a one-column band this wide is page-wide content.
FULL_WIDTH_RATIO = 0.6
# A wide image strip on a multi-column page is a spanning block.
INTERRUPTING_WIDTH_RATIO = 0.5

PageItemSource = generated.TextSpan | generated.ImageObject | generated.VectorObject


@dataclass
class PageItem:
    """One atomic page item for structural analysis (a line or a graphic)."""

    rect: generated.Rect
    span: generated.TextSpan | None = None
    image: generated.ImageObject | None = None
    vector: generated.VectorObject | None = None
    # Object sources of a merged graphic cluster (set by cluster_graphics).
    group: list[PageItemSource] = field(default_factory=list[PageItemSource])

    @property
    def is_image(self) -> bool:
        return self.image is not None

    @property
    def is_graphic(self) -> bool:
        """Images and vector drawings both behave as graphics structure."""
        return self.image is not None or self.vector is not None or bool(self.group)

    @property
    def object_ids(self) -> list[str]:
        if self.group:
            return [obj.id for obj in self.group]
        if self.image is not None:
            return [self.image.id]
        if self.vector is not None:
            return [self.vector.id]
        return []


@dataclass
class ColumnStructure:
    """One recovered column of a band, holding its items top-down."""

    rect: generated.Rect
    items: list[PageItem] = field(default_factory=list[PageItem])


@dataclass
class BandStructure:
    """One horizontal band of a page with its column structure."""

    band_id: str
    page_id: str
    layout_mode: str
    columns: list[ColumnStructure]
    index: int = 0

    @property
    def items(self) -> list[PageItem]:
        return [item for column in self.columns for item in column.items]

    @property
    def y_start(self) -> float:
        return min(item.rect.y for column in self.columns for item in column.items)

    @property
    def y_end(self) -> float:
        return max(
            item.rect.y + item.rect.height for column in self.columns for item in column.items
        )

    def has_images(self) -> bool:
        """True when any member item is a graphic (image or vector)."""
        return any(item.is_graphic for column in self.columns for item in column.items)


def items_from_objects(
    objects: Iterable[PageItemSource],
) -> list[PageItem]:
    """Wrap physical objects into structural items, reading order."""
    items: list[PageItem] = []
    for obj in objects:
        if isinstance(obj, generated.TextSpan):
            items.append(PageItem(rect=as_rect(obj.geometry), span=obj))
        elif isinstance(obj, generated.ImageObject):
            items.append(PageItem(rect=as_rect(obj.geometry), image=obj))
        else:
            items.append(PageItem(rect=as_rect(obj.geometry), vector=obj))
    items.sort(key=lambda item: (item.rect.y, item.rect.x))
    return items


# Graphic clustering (before column detection): a diagram must behave as
# one item or its internal x-gaps would split it across columns.
GRAPHIC_MERGE_GAP_PT = 12.0


def _merge_touching_graphic_clusters(
    clusters: list[list[PageItem]],
    gap: float,
) -> None:
    """Consolidate clusters that overlap or sit within ``gap`` of another.

    The single greedy pass can leave overlapping clusters behind when
    connector graphics (TikZ arrows) bridge boxes in an unfavorable visit
    order; consolidation runs to a fixpoint instead.
    """
    changed = True
    while changed:
        changed = False
        for i in range(len(clusters)):
            for j in range(i + 1, len(clusters)):
                a, b = _cluster_rect(clusters[i]), _cluster_rect(clusters[j])
                vertical_gap = max(a.y - (b.y + b.height), b.y - (a.y + a.height), 0.0)
                horizontal_gap = max(a.x - (b.x + b.width), b.x - (a.x + a.width), 0.0)
                if vertical_gap <= gap and horizontal_gap <= gap:
                    clusters[i].extend(clusters[j])
                    del clusters[j]
                    changed = True
                    break
            if changed:
                break


def cluster_graphics(items: list[PageItem]) -> list[PageItem]:
    """Merge nearby graphic items into single structural items.

    TikZ-style drawings arrive as many separate paths; a diagram's internal
    x-gaps would otherwise split it across detected columns. Text items
    pass through untouched.
    """
    graphics = [item for item in items if item.is_graphic]
    text_items = [item for item in items if not item.is_graphic]
    clusters: list[list[PageItem]] = []
    for item in sorted(graphics, key=lambda item: (item.rect.y, item.rect.x)):
        merged = False
        for cluster in clusters:
            reach_y = max(prev.rect.y + prev.rect.height for prev in cluster)
            left = min(prev.rect.x for prev in cluster)
            right = max(prev.rect.x + prev.rect.width for prev in cluster)
            horizontal_overlap = min(right, item.rect.x + item.rect.width) - max(left, item.rect.x)
            if item.rect.y - reach_y <= GRAPHIC_MERGE_GAP_PT and horizontal_overlap > 0:
                cluster.append(item)
                merged = True
                break
        if not merged:
            clusters.append([item])

    _merge_touching_graphic_clusters(clusters, GRAPHIC_MERGE_GAP_PT)

    result = list(text_items)
    for cluster in clusters:
        sources: list[PageItemSource] = []
        for member in cluster:
            if member.span is not None:
                sources.append(member.span)
            elif member.image is not None:
                sources.append(member.image)
            elif member.vector is not None:
                sources.append(member.vector)
            sources.extend(member.group)
        rect = _cluster_rect(cluster)
        first = cluster[0]
        result.append(PageItem(rect=rect, image=first.image, vector=first.vector, group=sources))
    result.sort(key=lambda item: (item.rect.y, item.rect.x))
    return result


def x_gutter_threshold(page_width: float) -> float:
    """Minimum x-gap that separates two columns of a page."""
    return max(GUTTER_MIN_RATIO * page_width, GUTTER_MIN_PT)


def _horizontal_strips(items: list[PageItem], min_gap: float) -> list[list[PageItem]]:
    """Split items into strips at full-width y-gaps."""
    ordered = sorted(items, key=lambda item: (item.rect.y, item.rect.x))
    strips: list[list[PageItem]] = [[ordered[0]]]
    reach = ordered[0].rect.y + ordered[0].rect.height
    for item in ordered[1:]:
        if item.rect.y - reach > min_gap:
            strips.append([item])
        else:
            strips[-1].append(item)
        reach = max(reach, item.rect.y + item.rect.height)
    return strips


def _vertical_columns(
    items: list[PageItem], min_gap: float, page_width: float
) -> list[list[PageItem]]:
    """Split items into columns at x-gaps spanning the full y-extent.

    Clusters narrower than :data:`MIN_COLUMN_RATIO` of the page are merged
    into the adjacent cluster they sit closest to: real columns are wide;
    narrow islands are equation numbers or table rules, not columns.
    """
    ordered = sorted(items, key=lambda item: (item.rect.x, item.rect.y))
    columns: list[list[PageItem]] = [[ordered[0]]]
    reach = ordered[0].rect.x + ordered[0].rect.width
    for item in ordered[1:]:
        if item.rect.x - reach > min_gap:
            columns.append([item])
        else:
            columns[-1].append(item)
        reach = max(reach, item.rect.x + item.rect.width)

    if len(columns) > 1:
        min_width = MIN_COLUMN_RATIO * page_width

        def _right_edge(members: list[PageItem]) -> float:
            rect = _cluster_rect(members)
            return rect.x + rect.width

        index = 0
        while index < len(columns):
            width = _cluster_rect(columns[index]).width
            if width >= min_width or len(columns) == 1:
                index += 1
                continue
            left_gap = (
                columns[index][0].rect.x - _right_edge(columns[index - 1])
                if index > 0
                else float("inf")
            )
            right_gap = (
                _cluster_rect(columns[index + 1]).x - _right_edge(columns[index])
                if index + 1 < len(columns)
                else float("inf")
            )
            target = index - 1 if left_gap <= right_gap else index + 1
            columns[target].extend(columns[index])
            del columns[index]
            columns.sort(key=lambda column: _cluster_rect(column).x)
        for column in columns:
            column.sort(key=lambda item: (item.rect.y, item.rect.x))
    return columns


def _cluster_rect(members: list[PageItem]) -> generated.Rect:
    rect = members[0].rect
    for member in members[1:]:
        x = min(rect.x, member.rect.x)
        y = min(rect.y, member.rect.y)
        rect = generated.Rect(
            kind="rect",
            x=x,
            y=y,
            width=max(rect.x + rect.width, member.rect.x + member.rect.width) - x,
            height=max(rect.y + rect.height, member.rect.y + member.rect.height) - y,
        )
    return rect


def detect_bands(
    *,
    page_id: str,
    page_width: float,
    items: list[PageItem],
) -> list[BandStructure]:
    """Recover the band/column structure of one page from raw items."""
    if not items:
        return []
    bands: list[BandStructure] = []
    _xy_cut(items, page_id, page_width, bands)
    page_has_multicolumn = any(len(band.columns) >= 2 for band in bands)
    for index, band in enumerate(bands):
        band.index = index
        band.layout_mode = _classify_band(band, page_width, page_has_multicolumn)
    return bands


def _xy_cut(
    items: list[PageItem],
    page_id: str,
    page_width: float,
    bands: list[BandStructure],
) -> None:
    """Recursive XY-cut: horizontal strips first, then columns."""
    strips = _horizontal_strips(items, HORIZONTAL_GAP_PT)
    if len(strips) > 1:
        for strip in strips:
            _xy_cut(strip, page_id, page_width, bands)
        return

    columns = _vertical_columns(items, x_gutter_threshold(page_width), page_width)
    if len(columns) > 1:
        bands.append(
            BandStructure(
                band_id="",
                page_id=page_id,
                layout_mode="MULTI_COLUMN",
                columns=[
                    ColumnStructure(rect=_cluster_rect(members), items=members)
                    for members in columns
                ],
            )
        )
        return

    bands.append(
        BandStructure(
            band_id="",
            page_id=page_id,
            layout_mode="SINGLE_COLUMN",
            columns=[ColumnStructure(rect=_cluster_rect(items), items=list(items))],
        )
    )


def reclassify_bands(
    bands: list[BandStructure],
    *,
    page_width: float,
    document_has_multicolumn: bool,
) -> None:
    """Re-classify bands with document-level column context.

    A spanning figure may occupy a whole page on its own; "spanning" is a
    property of the document's column layout, not of the single page.
    """
    for band in bands:
        band.layout_mode = _classify_band(band, page_width, document_has_multicolumn)


def _classify_band(
    band: BandStructure,
    page_width: float,
    page_has_multicolumn: bool,
) -> str:
    if len(band.columns) >= 2:
        return "MULTI_COLUMN"
    width_ratio = (band.columns[0].rect.width / page_width) if page_width > 0 else 0.0
    if (
        band.has_images()
        and width_ratio >= INTERRUPTING_WIDTH_RATIO
        and (page_has_multicolumn or width_ratio >= FULL_WIDTH_RATIO)
    ):
        # A wide graphic interrupts the column flow. In a single-column
        # document only clearly page-wide graphics count (>= FULL_WIDTH).
        return "SPANNING"
    if page_has_multicolumn and width_ratio >= FULL_WIDTH_RATIO:
        return "FULL_WIDTH"
    return "SINGLE_COLUMN"
