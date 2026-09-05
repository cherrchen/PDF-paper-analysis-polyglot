"""Phase 3.5 ReadingFlowGraph + Phase 3.6 paragraph continuation detection.

Reading order is derived from the band/column structure, never from a
global ``sort(y, x)``: bands are read top to bottom, columns left to
right, regions within a column top to bottom. Every edge carries a
ReadingOrderReason and a confidence; continuation between two text
regions (column break, page break, or interruption by a figure) overrides
the positional reason so semantic recovery (M4) can merge paragraphs.

Footnotes form their own FOOTNOTE_FLOW chain per page and are excluded
from the primary flow together with header/footer furniture.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import pairwise
from typing import TYPE_CHECKING

from pdf_pipeline.fusion import InternalRegion, dominant_label

if TYPE_CHECKING:
    from document_model.generated import schema_models as generated

    from pdf_pipeline.captions import CaptionAssociation

# Confidence per edge reason (Roadmap §4 Step 5: every edge observable).
CONFIDENCE_SAME_COLUMN = 0.9
CONFIDENCE_NEXT_COLUMN = 0.85
CONFIDENCE_SPANNING = 0.75
CONFIDENCE_FOOTNOTE_FLOW = 0.8

# Continuation scoring (Phase 3.6).
_CONTINUATION_BASE = 0.45
_CONTINUATION_LOWERCASE = 0.25
_CONTINUATION_FULL_LAST_LINE = 0.15
_CONTINUATION_THRESHOLD = 0.6
_FULL_LINE_RATIO = 0.85
_TERMINAL_PUNCTUATION = ".!?:"
# Trailing quotes/brackets do not terminate a sentence.
_TRAILING_CLOSERS = ")]}\"'”’»"  # noqa: RUF001 - typographic closers count


@dataclass
class FlowColumn:
    """Region-level view of one structural column."""

    rect: generated.Rect
    region_ids: list[str] = field(default_factory=list[str])


@dataclass
class FlowBand:
    """Region-level view of one band for flow construction."""

    layout_mode: str
    columns: list[FlowColumn]

    def ordered_region_ids(self) -> list[str]:
        return [region_id for column in self.columns for region_id in column.region_ids]

    def column_index_of(self, region_id: str) -> int:
        for index, column in enumerate(self.columns):
            if region_id in column.region_ids:
                return index
        return -1


@dataclass
class PageFlow:
    """Per-page inputs for the flow builder."""

    page_id: str
    bands: list[FlowBand] = field(default_factory=list[FlowBand])
    footnote_ids: list[str] = field(default_factory=list[str])


@dataclass
class FlowEdge:
    """A reading-flow edge before canonical serialization."""

    source: str
    target: str
    confidence: float
    reason: str


@dataclass
class FlowResult:
    """Reading flow graph plus its primary linearization."""

    nodes: list[str]
    edges: list[FlowEdge]
    primary_flow: list[str]


def _text_continuation_score(source: InternalRegion, target: InternalRegion) -> float | None:
    """Continuation likelihood for two adjacent text regions; None = no.

    Strong signal: the source text does not end a sentence (no terminal
    punctuation after stripping closers). Supporting signals: the target
    starts lowercase, and the source's last line filled its block width
    (the line was broken at a column/page/figure boundary, not ended).
    """
    if source.kind != "TEXT" or target.kind != "TEXT":
        return None
    if any(
        dominant_label(region) in {"HEADING_LIKE", "CAPTION_LIKE", "FOOTNOTE"}
        for region in (source, target)
    ):
        return None
    text = source.text.strip()
    if not text:
        return None
    while text and text[-1] in _TRAILING_CLOSERS:
        text = text[:-1].rstrip()
    if not text or text[-1] in _TERMINAL_PUNCTUATION:
        return None

    score = _CONTINUATION_BASE
    target_text = target.text.strip()
    if target_text and target_text[0].islower():
        score += _CONTINUATION_LOWERCASE
    last_line = source.last_line
    if (
        last_line is not None
        and source.rect.width > 0
        and last_line.rect.width >= _FULL_LINE_RATIO * source.rect.width
    ):
        score += _CONTINUATION_FULL_LAST_LINE
    if score < _CONTINUATION_THRESHOLD:
        return None
    return round(min(score, 0.95), 4)


def _positional_reason(  # noqa: PLR0911 - one return per positional relation
    *,
    source: InternalRegion,
    target: InternalRegion,
    source_band: FlowBand | None,
    target_band: FlowBand | None,
    same_page: bool,
    target_page_multicolumn: bool,
) -> tuple[str, float]:
    """Positional edge reason from the band/column structure."""
    if source_band is not None and source_band is target_band:
        if source_band.layout_mode == "MULTI_COLUMN" and source_band.column_index_of(
            source.region_id
        ) != source_band.column_index_of(target.region_id):
            return "NEXT_COLUMN", CONFIDENCE_NEXT_COLUMN
        return "SAME_COLUMN", CONFIDENCE_SAME_COLUMN

    if source_band is None or target_band is None:
        # Region without a flow band (furniture corner case): keep the
        # default document order.
        return "SAME_COLUMN", CONFIDENCE_SAME_COLUMN
    if target_band.layout_mode == "SPANNING" and source_band.layout_mode != "SPANNING":
        return "BEFORE_SPANNING_BLOCK", CONFIDENCE_SPANNING
    if source_band.layout_mode == "SPANNING" and target_band.layout_mode != "SPANNING":
        return "AFTER_SPANNING_BLOCK", CONFIDENCE_SPANNING
    if source_band.layout_mode == "MULTI_COLUMN" and target_band.layout_mode == "FULL_WIDTH":
        return "BEFORE_SPANNING_BLOCK", CONFIDENCE_SPANNING
    if source_band.layout_mode == "FULL_WIDTH" and target_band.layout_mode == "MULTI_COLUMN":
        return "AFTER_SPANNING_BLOCK", CONFIDENCE_SPANNING
    if not same_page:
        return (
            ("NEXT_COLUMN", CONFIDENCE_NEXT_COLUMN)
            if target_page_multicolumn
            else ("SAME_COLUMN", CONFIDENCE_SAME_COLUMN)
        )
    if source_band.layout_mode == "MULTI_COLUMN" and target_band.layout_mode == "MULTI_COLUMN":
        # Same column position across a structural break keeps the flow;
        # a different x position is a column wrap.
        source_column = source_band.columns[source_band.column_index_of(source.region_id)]
        target_column = target_band.columns[target_band.column_index_of(target.region_id)]
        tolerance = max(4.0, 0.02 * max(source_column.rect.width, target_column.rect.width))
        if abs(source_column.rect.x - target_column.rect.x) <= tolerance:
            return "SAME_COLUMN", CONFIDENCE_SAME_COLUMN
        return "NEXT_COLUMN", CONFIDENCE_NEXT_COLUMN
    return "SAME_COLUMN", CONFIDENCE_SAME_COLUMN


def _page_chain(
    page: PageFlow,
    regions_by_id: dict[str, InternalRegion],
    primary_flow: list[str],
) -> list[InternalRegion]:
    """Main-flow regions of a page in band/column order.

    Footnotes, headers, and footers stay out; content that landed on no
    flow band still joins the primary flow at the end of its page.
    """
    chain: list[InternalRegion] = []
    band_placed: set[str] = set()
    for band in page.bands:
        for region_id in band.ordered_region_ids():
            band_placed.add(region_id)
            region = regions_by_id.get(region_id)
            if region is not None and region.kind not in {"FOOTNOTE", "HEADER", "FOOTER"}:
                chain.append(region)
    for region_id, region in regions_by_id.items():
        if (
            region.page_id == page.page_id
            and region_id not in band_placed
            and region.kind not in {"FOOTNOTE", "HEADER", "FOOTER"}
        ):
            chain.append(region)
    primary_flow.extend(region.region_id for region in chain)
    return chain


def _flow_nodes(pages: list[PageFlow], regions_by_id: dict[str, InternalRegion]) -> list[str]:
    """Graph nodes: flow-band regions, footnotes, then any leftovers."""
    nodes: list[str] = []
    placed: set[str] = set()
    for page in pages:
        for band in page.bands:
            for region_id in band.ordered_region_ids():
                if region_id not in placed:
                    nodes.append(region_id)
                    placed.add(region_id)
        nodes.extend(rid for rid in page.footnote_ids if rid not in placed and rid in regions_by_id)
        placed.update(nodes)
    nodes.extend(region_id for region_id in regions_by_id if region_id not in placed)
    return nodes


def _chain_adjacent(edges: list[FlowEdge], source_id: str, target_id: str) -> bool:
    return any(edge.source == source_id and edge.target == target_id for edge in edges)


def _caption_override(
    source_id: str,
    target_id: str,
    reason: str,
    confidence: float,
    *,
    caption_of: dict[str, CaptionAssociation],
    main_of: dict[str, CaptionAssociation],
) -> tuple[str, float]:
    """Upgrade a positional edge to CAPTION_ASSOCIATION when it joins a
    recovered figure/table↔caption pair (either direction)."""
    association = main_of.get(source_id)
    if association is not None and association.caption_region_id == target_id:
        return "CAPTION_ASSOCIATION", association.score
    caption_assoc = caption_of.get(source_id)
    if caption_assoc is not None and caption_assoc.main_region_id == target_id:
        return "CAPTION_ASSOCIATION", caption_assoc.score
    return reason, confidence


def build_reading_flow(
    pages: list[PageFlow],
    regions_by_id: dict[str, InternalRegion],
    caption_associations: list[CaptionAssociation],
) -> FlowResult:
    """Build the document-wide reading flow graph and primary flow.

    ``caption_associations`` upgrade main↔caption chain edges to
    CAPTION_ASSOCIATION. Text regions interrupted by non-text regions get
    an extra CONTINUATION edge when their content continues.
    """
    caption_of: dict[str, CaptionAssociation] = {
        association.caption_region_id: association for association in caption_associations
    }
    main_of: dict[str, CaptionAssociation] = {
        association.main_region_id: association for association in caption_associations
    }

    band_of: dict[str, FlowBand] = {}
    for page in pages:
        for band in page.bands:
            for region_id in band.ordered_region_ids():
                band_of[region_id] = band

    nodes = _flow_nodes(pages, regions_by_id)

    edges: list[FlowEdge] = []
    primary_flow: list[str] = []
    last_main_text: InternalRegion | None = None
    previous: tuple[InternalRegion, FlowBand | None, str] | None = None

    for page in pages:
        chain = _page_chain(page, regions_by_id, primary_flow)

        page_has_multicolumn = any(band.layout_mode == "MULTI_COLUMN" for band in page.bands)
        for region in chain:
            if previous is not None:
                source, source_band, source_page_id = previous
                reason, confidence = _positional_reason(
                    source=source,
                    target=region,
                    source_band=source_band,
                    target_band=band_of.get(region.region_id),
                    same_page=source_page_id == page.page_id,
                    target_page_multicolumn=page_has_multicolumn,
                )
                reason, confidence = _caption_override(
                    source.region_id,
                    region.region_id,
                    reason,
                    confidence,
                    caption_of=caption_of,
                    main_of=main_of,
                )
                continuation = _text_continuation_score(source, region)
                if continuation is not None:
                    reason, confidence = "CONTINUATION", continuation
                edges.append(
                    FlowEdge(
                        source=source.region_id,
                        target=region.region_id,
                        confidence=confidence,
                        reason=reason,
                    )
                )

            # Phase 3.6: continuation across an interruption (figure,
            # table, formula) between the last text region and this one.
            if region.kind == "TEXT":
                if (
                    last_main_text is not None
                    and last_main_text.region_id != region.region_id
                    and not _chain_adjacent(edges, last_main_text.region_id, region.region_id)
                ):
                    continuation = _text_continuation_score(last_main_text, region)
                    if continuation is not None:
                        edges.append(
                            FlowEdge(
                                source=last_main_text.region_id,
                                target=region.region_id,
                                confidence=continuation,
                                reason="CONTINUATION",
                            )
                        )
                last_main_text = region

            previous = (region, band_of.get(region.region_id), page.page_id)

    # Footnote sub-flows: separate chains, never part of the primary flow.
    for page in pages:
        ordered = [
            regions_by_id[region_id]
            for region_id in sorted(
                page.footnote_ids,
                key=lambda rid: (
                    regions_by_id[rid].rect.y,
                    regions_by_id[rid].rect.x,
                ),
            )
            if region_id in regions_by_id
        ]
        for source, target in pairwise(ordered):
            edges.append(
                FlowEdge(
                    source=source.region_id,
                    target=target.region_id,
                    confidence=CONFIDENCE_FOOTNOTE_FLOW,
                    reason="FOOTNOTE_FLOW",
                )
            )

    return FlowResult(nodes=nodes, edges=edges, primary_flow=primary_flow)


__all__ = [
    "FlowBand",
    "FlowColumn",
    "FlowEdge",
    "FlowResult",
    "PageFlow",
    "build_reading_flow",
]
