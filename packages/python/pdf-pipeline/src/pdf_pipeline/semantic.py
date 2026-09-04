"""Phase 2.3 minimal semantic recovery: LayoutDocument -> SemanticDocument.

Walking Skeleton scope: HEADING, PARAGRAPH, FIGURE, and FIGURE_CAPTION
nodes only. Captions are recovered with a naive heuristic (short text
region directly below a figure region). Semantic nodes carry no geometry;
source positions live in the mapping layer (Phase 2.6).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from document_model.generated import schema_models as generated

from pdf_pipeline.ids import stable_uuid

if TYPE_CHECKING:
    from document_model.generated.schema_models import LayoutRegion

SEMANTIC_PRODUCER = "pdf-pipeline.semantic"

# Caption heuristic bounds (deliberately naive; quality is an M3+ concern).
CAPTION_MAX_CHARS = 300
CAPTION_MAX_Y_DISTANCE_PT = 60.0
CAPTION_MIN_Y_OVERLAP_RATIO = 0.1

CONFIDENCE_HEADING = 0.6
CONFIDENCE_PARAGRAPH = 0.8
CONFIDENCE_FIGURE = 0.7
CONFIDENCE_CAPTION = 0.5


def _heading_level(region: LayoutRegion) -> int:
    """Heading depth from the region's y-position within the heading-like
    set is unknowable without font metadata; M2 uses a flat level 1."""
    return 1


def _region_label(region: LayoutRegion) -> str | None:
    for label in region.labels:
        return label.label
    return None


def _is_caption_below(text_region: LayoutRegion, figure_region: LayoutRegion) -> bool:
    """Naive caption heuristic: short text region just below a figure."""
    caption = text_region.geometry
    figure = figure_region.geometry
    if not isinstance(caption, generated.Rect) or not isinstance(figure, generated.Rect):
        return False
    vertical_gap = caption.y - (figure.y + figure.height)
    if vertical_gap < 0 or vertical_gap > CAPTION_MAX_Y_DISTANCE_PT:
        return False
    horizontal_overlap = min(caption.x + caption.width, figure.x + figure.width) - max(
        caption.x, figure.x
    )
    if horizontal_overlap <= 0:
        return False
    overlap_ratio = horizontal_overlap / min(caption.width, figure.width)
    return overlap_ratio >= CAPTION_MIN_Y_OVERLAP_RATIO


def _assign_captions(
    regions_by_page: dict[str, list[LayoutRegion]],
) -> dict[str, str]:
    """First-fit caption assignment per page.

    Each text region captions at most one figure; each figure receives at
    most one caption.
    """
    caption_of: dict[str, str] = {}
    for regions in regions_by_page.values():
        page_figures = [r for r in regions if r.kind == "FIGURE"]
        page_texts = [r for r in regions if r.kind == "TEXT"]
        assigned: set[str] = set()
        for text_region in page_texts:
            for figure in page_figures:
                if figure.id in assigned or text_region.id in caption_of:
                    continue
                if _is_caption_below(text_region, figure):
                    caption_of[text_region.id] = figure.id
                    assigned.add(figure.id)
                    break
    return caption_of


def recover_semantic_document(
    layout: generated.LayoutDocument,
    region_texts: dict[str, str],
) -> generated.SemanticDocument:
    """Build a minimal SemanticDocument.

    ``region_texts`` maps layout region id -> extracted text for TEXT
    regions. Produces HEADING, PARAGRAPH, FIGURE, and FIGURE_CAPTION nodes
    under a single DOCUMENT root, with CAPTION_OF relations for recovered
    captions.
    """
    nodes: list[generated.SemanticNode] = []
    relations: list[generated.SemanticRelation] = []

    document_id = stable_uuid(layout.id, "semantic-document")
    root_id = stable_uuid(layout.id, "node", "root")
    nodes.append(
        generated.SemanticNode(
            id=root_id,
            kind="DOCUMENT",
            parentId=None,
            children=[],
            content=generated.RichText(text="", marks=[]),
            attributes={},
            confidence=generated.NodeConfidence(score=1.0, reason="document root"),
            provenanceIds=[],
        )
    )

    regions_by_page: dict[str, list[LayoutRegion]] = {}
    for region in layout.regions:
        regions_by_page.setdefault(region.pageId, []).append(region)

    caption_of = _assign_captions(regions_by_page)

    def _make_node(
        kind: generated.NodeKind,
        *,
        parent_id: str,
        content: generated.RichText | generated.FigureContent,
        score: float,
        reason: str,
        attributes: dict[str, Any] | None = None,
    ) -> str:
        node_id = stable_uuid(layout.id, "node", len(nodes))
        nodes.append(
            generated.SemanticNode(
                id=node_id,
                kind=kind,
                parentId=parent_id,
                children=[],
                content=content,
                attributes=attributes or {},
                confidence=generated.NodeConfidence(score=score, reason=reason),
                provenanceIds=[],
            )
        )
        return node_id

    def _make_text_node(
        kind: generated.NodeKind,
        region_id: str,
        score: float,
        reason: str,
        attributes: dict[str, Any] | None = None,
    ) -> str:
        text = region_texts.get(region_id, "")
        return _make_node(
            kind,
            parent_id=root_id,
            content=generated.RichText(text=text, marks=[]),
            score=score,
            reason=reason,
            attributes=attributes,
        )

    def _make_figure_node() -> str:
        return _make_node(
            "FIGURE",
            parent_id=root_id,
            content=generated.FigureContent(
                resources=generated.FigureResource(embeddedImageIds=[]),
            ),
            score=CONFIDENCE_FIGURE,
            reason="layout figure region",
        )

    for regions in regions_by_page.values():
        # Interleave in reading order: figures and text in primaryFlow order.
        flow_order = [rid for rid in layout.primaryFlow if rid in {r.id for r in regions}]
        ordered_regions = {r.id: r for r in regions}
        figure_nodes: dict[str, str] = {}
        for region_id in flow_order:
            region = ordered_regions[region_id]
            label = _region_label(region)
            if region.kind == "FIGURE":
                figure_nodes[region.id] = _make_figure_node()
            elif region.id in caption_of:
                node_id = _make_text_node(
                    "FIGURE_CAPTION", region.id, CONFIDENCE_CAPTION, "caption below figure"
                )
                figure_node = figure_nodes.get(caption_of[region.id])
                if figure_node is not None:
                    relations.append(
                        generated.SemanticRelation(
                            id=stable_uuid(layout.id, "rel", len(relations)),
                            type="CAPTION_OF",
                            source=node_id,
                            target=figure_node,
                            confidence=CONFIDENCE_CAPTION,
                            provenanceIds=[],
                        )
                    )
            elif region.kind == "TEXT" and label == "HEADING_LIKE":
                _make_text_node(
                    "HEADING",
                    region.id,
                    CONFIDENCE_HEADING,
                    "font-size heuristic",
                    attributes={"level": _heading_level(region)},
                )
            elif region.kind == "TEXT" and region_texts.get(region.id, "").strip():
                _make_text_node("PARAGRAPH", region.id, CONFIDENCE_PARAGRAPH, "layout text region")

    root = nodes[0]
    nodes[0] = root.model_copy(update={"children": [node.id for node in nodes[1:]]})

    return generated.SemanticDocument(
        schemaVersion="0.1.0",
        id=document_id,
        layoutDocumentId=layout.id,
        rootId=root_id,
        nodes=nodes,
        relations=relations,
        provenanceIds=[],
    )
