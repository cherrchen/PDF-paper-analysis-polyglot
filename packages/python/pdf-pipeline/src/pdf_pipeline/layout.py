"""M3 layout recovery orchestration: PhysicalDocument + Evidence -> LayoutDocument.

Stage order (Roadmap M3):

1. Evidence collection + normalization (Phase 3.1, ``pdf_pipeline.evidence``)
2. Band/column detection on raw page items (Phase 3.3/3.4,
   ``pdf_pipeline.page_structure``) — full-width lines must not bridge
   columns, so structure comes before text blocking.
3. Per-column text blocking + figure clustering (``pdf_pipeline.blocks``)
4. Region fusion into internal regions (Phase 3.2, ``pdf_pipeline.fusion``)
5. Caption association (Phase 3.7, ``pdf_pipeline.captions``)
6. Footnote recovery (Phase 3.8, ``pdf_pipeline.footnotes``)
7. Reading flow graph + continuation (Phase 3.5/3.6,
   ``pdf_pipeline.reading_flow``)

Every stage is deterministic: identical input bytes yield identical
LayoutDocument bytes. Confidence, reasons, evidence ids, and provenance
are carried end to end (Roadmap §4 Step 5).
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, cast

from document_model.generated import schema_models as generated

from pdf_pipeline.blocks import (
    build_figure_drafts,
    build_furniture_drafts,
    build_text_block_drafts,
)
from pdf_pipeline.captions import CaptionAssociation, associate_captions
from pdf_pipeline.evidence.normalize import NormalizedCandidate, normalize_bundle
from pdf_pipeline.evidence.providers import EvidenceProvider, MockLayoutEvidenceProvider
from pdf_pipeline.footnotes import detect_footnote_ids
from pdf_pipeline.furniture import body_font_size, split_furniture
from pdf_pipeline.fusion import fuse_page
from pdf_pipeline.geometry import containment
from pdf_pipeline.ids import stable_uuid
from pdf_pipeline.page_structure import (
    BandStructure,
    cluster_graphics,
    detect_bands,
    items_from_objects,
    reclassify_bands,
)
from pdf_pipeline.reading_flow import FlowBand, FlowColumn, PageFlow, build_reading_flow

if TYPE_CHECKING:
    from collections.abc import Iterable

    from pdf_pipeline.fusion import InternalRegion, RegionDraft
    from pdf_pipeline.reading_flow import FlowEdge

LAYOUT_PRODUCER = "pdf-pipeline.layout"
LAYOUT_PRODUCER_VERSION = "0.1.0"


def recover_layout_document(
    physical: generated.PhysicalDocument,
    *,
    providers: Iterable[EvidenceProvider] | None = None,
    evidence: generated.EvidenceBundle | None = None,
) -> generated.LayoutDocument:
    """Recover the LayoutDocument of a PhysicalDocument.

    ``evidence`` injects a pre-built bundle (e.g. from a real parser
    adapter); by default the deterministic mock provider runs so the
    pipeline needs no third-party dependency.
    """
    bundles = (
        [evidence]
        if evidence is not None
        else [
            provider.collect(physical) for provider in (providers or [MockLayoutEvidenceProvider()])
        ]
    )
    candidates_by_page: dict[str, list[NormalizedCandidate]] = {}
    for bundle in bundles:
        for candidate in normalize_bundle(bundle, physical):
            candidates_by_page.setdefault(candidate.pageId, []).append(candidate)

    fingerprint = physical.sourceFingerprint or physical.id
    recovery = _PageRecovery(
        physical=physical,
        fingerprint=fingerprint,
        candidates_by_page=candidates_by_page,
    )
    for page_index, page in enumerate(physical.pages):
        recovery.recover_page(page, page_index)
    recovery.finalize()

    flow = build_reading_flow(recovery.page_flows, recovery.regions_by_id, recovery.associations)

    return _assemble(
        physical=physical,
        recovery=recovery,
        fingerprint=fingerprint,
        nodes=flow.nodes,
        edges=flow.edges,
        primary_flow=flow.primary_flow,
    )


class _PageRecovery:
    """Mutable per-page accumulator consumed by layout assembly."""

    def __init__(
        self,
        *,
        physical: generated.PhysicalDocument,
        fingerprint: str,
        candidates_by_page: dict[str, list[NormalizedCandidate]],
    ) -> None:
        self._physical = physical
        self._fingerprint = fingerprint
        self._candidates_by_page = candidates_by_page
        self.regions_by_id: dict[str, InternalRegion] = {}
        self.page_flows: list[PageFlow] = []
        self.structural_bands: list[list[BandStructure]] = []
        self._pages_bands: list[tuple[generated.PhysicalPage, list[BandStructure]]] = []
        self._pages_footnote_ids: list[list[str]] = []
        self.associations: list[CaptionAssociation] = []

    def recover_page(self, page: generated.PhysicalPage, page_index: int) -> None:
        spans: list[generated.TextSpan] = []
        images: list[generated.ImageObject] = []
        vectors: list[generated.VectorObject] = []
        for obj in self._physical.objects:
            if obj.pageId != page.id:
                continue
            if obj.objectType == "textSpan":
                spans.append(obj)
            elif obj.objectType == "imageObject":
                images.append(obj)
            elif obj.objectType == "vectorObject":
                vectors.append(obj)

        body_font = body_font_size(spans)
        body, headers, footers = split_furniture(spans, page.geometry.heightPt, body_font)
        items = cluster_graphics(
            items_from_objects([*body, *images, *vectors])  # type: ignore[arg-type]
        )

        bands = detect_bands(
            page_id=page.id,
            page_width=page.geometry.widthPt,
            items=items,
        )
        for band_ordinal, band in enumerate(bands):
            band.band_id = stable_uuid(self._fingerprint, "band", page_index, band_ordinal)
        self._pages_bands.append((page, bands))

        drafts: list[RegionDraft] = []
        for band in bands:
            for column_ordinal, column in enumerate(band.columns):
                drafts.extend(
                    build_text_block_drafts(
                        page_id=page.id,
                        fingerprint=self._fingerprint,
                        page_index=page_index,
                        column_tag=(band.index, column_ordinal),
                        items=[item for item in column.items if item.span],
                        body_font=body_font,
                        start_ordinal=len(drafts),
                    )
                )
                drafts.extend(
                    build_figure_drafts(
                        page_id=page.id,
                        fingerprint=self._fingerprint,
                        page_index=page_index,
                        column_tag=(band.index, column_ordinal),
                        items=[item for item in column.items if item.is_graphic],
                        start_ordinal=len(drafts),
                    )
                )
        drafts.extend(
            build_furniture_drafts(
                page_id=page.id,
                fingerprint=self._fingerprint,
                page_index=page_index,
                headers=headers,
                footers=footers,
                start_ordinal=len(drafts),
            )
        )

        # Region ids must be unique per document: offset by the count of
        # regions recovered so far.
        region_counter = len(self.regions_by_id)

        def unique_region_id_fn(ordinal: int) -> str:
            return stable_uuid(self._fingerprint, "region", page_index, ordinal + region_counter)

        regions = fuse_page(
            drafts=drafts,
            candidates=self._candidates_by_page.get(page.id, []),
            region_id_fn=unique_region_id_fn,
        )
        regions = self._assign_orphan_columns(regions, bands, page.geometry.widthPt)

        # Phase 3.8: mark footnote regions so they leave the primary flow.
        footnote_ids = detect_footnote_ids(
            regions, page_height=page.geometry.heightPt, body_font=body_font
        )
        footnote_set = set(footnote_ids)
        regions = [
            replace(
                region,
                kind="FOOTNOTE",
                labels=(
                    generated.LayoutLabelCandidate(
                        label="FOOTNOTE",
                        confidence=0.8,
                        evidenceIds=[],
                    ),
                    *region.labels,
                ),
            )
            if region.region_id in footnote_set
            else region
            for region in regions
        ]
        for region in regions:
            self.regions_by_id[region.region_id] = region

        self.associations.extend(associate_captions(regions))
        self.structural_bands.append(bands)
        self._pages_footnote_ids.append(footnote_ids)

    def finalize(self) -> None:
        """Second band classification pass, then region-level flow bands.

        SPANNING/FULL_WIDTH depend on the document's column layout, so the
        final classification runs once every page's bands are known.
        """
        document_has_multicolumn = any(
            band.layout_mode == "MULTI_COLUMN" for bands in self.structural_bands for band in bands
        )
        if document_has_multicolumn:
            for page, bands in self._pages_bands:
                reclassify_bands(
                    bands, page_width=page.geometry.widthPt, document_has_multicolumn=True
                )
        for (page, bands), footnote_ids in zip(
            self._pages_bands, self._pages_footnote_ids, strict=True
        ):
            flow_bands: list[FlowBand] = []
            for band in bands:
                flow_columns: list[FlowColumn] = []
                for column_ordinal, column in enumerate(band.columns):
                    tag = (band.index, column_ordinal)
                    member_ids: list[str] = [
                        region.region_id
                        for region in sorted(
                            (
                                r
                                for r in self.regions_by_id.values()
                                if r.column_tag == tag and r.page_id == page.id
                            ),
                            key=lambda region: (region.rect.y, region.rect.x),
                        )
                    ]
                    flow_columns.append(FlowColumn(rect=column.rect, region_ids=member_ids))
                flow_bands.append(FlowBand(layout_mode=band.layout_mode, columns=flow_columns))
            self.page_flows.append(
                PageFlow(page_id=page.id, bands=flow_bands, footnote_ids=footnote_ids)
            )

    def _assign_orphan_columns(
        self,
        regions: list[InternalRegion],
        bands: list[BandStructure],
        page_width: float,
    ) -> list[InternalRegion]:
        """Give evidence-only regions a column by geometry containment."""
        assigned: list[InternalRegion] = []
        for region in regions:
            if region.column_tag is not None:
                assigned.append(region)
                continue
            best_tag: tuple[int, int] | None = None
            best_score = 0.0
            for band in bands:
                for column_ordinal, column in enumerate(band.columns):
                    score = containment(region.rect, column.rect)
                    if score > best_score:
                        best_score = score
                        best_tag = (band.index, column_ordinal)
            if best_tag is None and bands:
                # Fall back to the horizontal mid-point: columns are
                # left-to-right ordered, so half the page width splits them.
                center_x = region.rect.x + region.rect.width / 2
                band = bands[0]
                best_tag = (band.index, 0 if center_x < page_width / 2 else len(band.columns) - 1)
            assigned.append(replace(region, column_tag=best_tag))
        return assigned


def _assemble(
    *,
    physical: generated.PhysicalDocument,
    recovery: _PageRecovery,
    fingerprint: str,
    nodes: list[str],
    edges: list[FlowEdge],
    primary_flow: list[str],
) -> generated.LayoutDocument:
    regions: list[generated.LayoutRegion] = []
    provenance_records: list[generated.ProvenanceRecord] = []
    for region in recovery.regions_by_id.values():
        labels = [
            generated.LayoutLabelCandidate(
                label=label.label,
                confidence=label.confidence,
                evidenceIds=list(region.evidence_ids) if index == 0 else [],
            )
            for index, label in enumerate(region.labels)
        ]
        regions.append(
            generated.LayoutRegion(
                id=region.region_id,
                pageId=region.page_id,
                geometry=region.rect,
                kind=region.kind,
                childIds=[],
                physicalObjectIds=list(region.physical_object_ids),
                labels=labels,
                confidence=region.confidence,
                provenanceIds=[],
            )
        )
        if region.evidence_ids:
            provenance_records.append(
                generated.ProvenanceRecord(
                    id=stable_uuid(fingerprint, "layout-prov", region.region_id),
                    producer=LAYOUT_PRODUCER,
                    producerVersion=LAYOUT_PRODUCER_VERSION,
                    operation="region-fusion",
                    inputRefs=list(region.evidence_ids),
                )
            )

    pages: list[generated.LayoutPage] = []
    bands: list[generated.PageBand] = []
    columns: list[generated.Column] = []
    for structural_bands, flow_page, physical_page in zip(
        recovery.structural_bands, recovery.page_flows, physical.pages, strict=True
    ):
        page_band_ids: list[str] = []
        page_region_ids: list[str] = []
        for band in structural_bands:
            column_ids: list[str] = []
            for column_ordinal, column in enumerate(band.columns):
                column_id = stable_uuid(
                    fingerprint, "col", physical_page.index, band.index, column_ordinal
                )
                column_ids.append(column_id)
                member_ids = [
                    region.region_id
                    for region in sorted(
                        _regions_of_column(recovery, band, column_ordinal),
                        key=lambda region: (region.rect.y, region.rect.x),
                    )
                ]
                columns.append(
                    generated.Column(
                        id=column_id,
                        pageId=flow_page.page_id,
                        bandId=band.band_id,
                        geometry=column.rect,
                        regionIds=member_ids,
                    )
                )
                page_region_ids.extend(member_ids)
            band_rect = _items_rect(band)
            bands.append(
                generated.PageBand(
                    id=band.band_id,
                    pageId=flow_page.page_id,
                    yStart=band_rect.y,
                    yEnd=band_rect.y + band_rect.height,
                    layoutMode=cast("generated.BandLayoutMode", band.layout_mode),
                    columnIds=column_ids,
                )
            )
            page_band_ids.append(band.band_id)

        # Any region not covered by a column (empty-page corner cases)
        # still belongs to its page.
        page_region_set = set(page_region_ids)
        leftovers = [
            region.region_id
            for region in recovery.regions_by_id.values()
            if region.page_id == flow_page.page_id and region.region_id not in page_region_set
        ]
        pages.append(
            generated.LayoutPage(
                pageId=flow_page.page_id,
                regionIds=page_region_ids + leftovers,
                bandIds=page_band_ids,
            )
        )

    groups: list[generated.LayoutGroup] = []
    for association in recovery.associations:
        main = recovery.regions_by_id[association.main_region_id]
        groups.append(
            generated.LayoutGroup(
                id=stable_uuid(fingerprint, "group", association.main_region_id),
                kind=cast("generated.LayoutGroupKind", association.group_kind),
                memberIds=[association.main_region_id, association.caption_region_id],
                pageId=main.page_id,
                confidence=generated.LayoutConfidence(
                    score=association.score,
                    reason="caption-association",
                ),
            )
        )

    reading_edges = [
        generated.ReadingEdge(
            source=edge.source,
            target=edge.target,
            confidence=edge.confidence,
            reason=cast("generated.ReadingOrderReason", edge.reason),
        )
        for edge in edges
    ]

    return generated.LayoutDocument(
        schemaVersion="0.1.0",
        id=stable_uuid(fingerprint, "layout-document"),
        physicalDocumentId=physical.id,
        pages=pages,
        regions=regions,
        bands=bands,
        columns=columns,
        groups=groups,
        readingFlow=generated.ReadingFlowGraph(nodes=nodes, edges=reading_edges),
        primaryFlow=primary_flow,
        provenance=generated.ProvenanceStore(records=provenance_records),
    )


def _regions_of_column(
    recovery: _PageRecovery,
    band: BandStructure,
    column_ordinal: int,
) -> list[InternalRegion]:
    tag = (band.index, column_ordinal)
    return [
        region
        for region in recovery.regions_by_id.values()
        if region.column_tag == tag and region.page_id == band.page_id
    ]


def _items_rect(band: BandStructure) -> generated.Rect:
    items = band.items
    rect = items[0].rect
    for item in items[1:]:
        x = min(rect.x, item.rect.x)
        y = min(rect.y, item.rect.y)
        rect = generated.Rect(
            kind="rect",
            x=x,
            y=y,
            width=max(rect.x + rect.width, item.rect.x + item.rect.width) - x,
            height=max(rect.y + rect.height, item.rect.y + item.rect.height) - y,
        )
    return rect
