"""Semantic recovery: LayoutDocument -> SemanticDocument (M3 updated).

The semantic layer owns paper semantics and carries no geometry. Since M3
it consumes the layout layer's caption associations (FIGURE_BLOCK /
TABLE_BLOCK groups) instead of re-deriving them geometrically, creates
FOOTNOTE nodes for layout footnote regions (footnotes stay outside the
primary flow), and records each node's source region in ``attributes``
so the mapping layer pairs anchors without positional guesswork.

Table regions are recovered at layout level only in M3; TABLE semantic
nodes arrive with the semantic recovery engine (M4).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from document_model.generated import schema_models as generated

from pdf_pipeline.ids import stable_uuid

if TYPE_CHECKING:
    from document_model.generated.schema_models import LayoutRegion

SEMANTIC_PRODUCER = "pdf-pipeline.semantic"

CONFIDENCE_HEADING = 0.6
CONFIDENCE_PARAGRAPH = 0.8
CONFIDENCE_FIGURE = 0.7
CONFIDENCE_CAPTION = 0.7
CONFIDENCE_FOOTNOTE = 0.7


def _region_label(region: LayoutRegion) -> str | None:
    for label in region.labels:
        return label.label
    return None


def _caption_bindings(
    layout: generated.LayoutDocument,
    regions_by_id: dict[str, LayoutRegion],
) -> dict[str, str]:
    """Caption region id -> main region id, from layout groups."""
    bindings: dict[str, str] = {}
    for group in layout.groups:
        if group.kind not in {"FIGURE_BLOCK", "TABLE_BLOCK"} or len(group.memberIds) != 2:
            continue
        main, caption = (regions_by_id.get(member) for member in group.memberIds)
        if main is None or caption is None:
            continue
        if main.kind in {"FIGURE", "TABLE"} and caption.kind == "TEXT":
            bindings[caption.id] = main.id
        elif caption.kind in {"FIGURE", "TABLE"} and main.kind == "TEXT":
            bindings[main.id] = caption.id
    return bindings


def recover_semantic_document(
    layout: generated.LayoutDocument,
    region_texts: dict[str, str],
) -> generated.SemanticDocument:
    """Build the SemanticDocument from a recovered LayoutDocument.

    Nodes are created in primary-flow order (headers, footers, and
    footnotes excluded by layout); footnote nodes follow at the end, so
    the document root's child order is the reading order of the paper.
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

    regions_by_id = {region.id: region for region in layout.regions}
    caption_bindings = _caption_bindings(layout, regions_by_id)
    figure_region_nodes: dict[str, str] = {}

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
        region: LayoutRegion,
        score: float,
        reason: str,
        attributes: dict[str, Any] | None = None,
    ) -> str:
        return _make_node(
            kind,
            parent_id=root_id,
            content=generated.RichText(text=region_texts.get(region.id, ""), marks=[]),
            score=score,
            reason=reason,
            attributes={**(attributes or {}), "layoutRegionId": region.id},
        )

    def _make_figure_node(region: LayoutRegion) -> str:
        return _make_node(
            "FIGURE",
            parent_id=root_id,
            content=generated.FigureContent(
                resources=generated.FigureResource(embeddedImageIds=list(region.physicalObjectIds)),
            ),
            score=CONFIDENCE_FIGURE,
            reason="layout figure region",
            attributes={"layoutRegionId": region.id},
        )

    def _region_for_flow(region_id: str) -> None:
        region = regions_by_id[region_id]
        label = _region_label(region)
        if region.kind == "FIGURE":
            figure_region_nodes[region.id] = _make_figure_node(region)
        elif region.kind == "TABLE":
            # Table content recovery is semantic recovery (M4); the layout
            # TABLE region is intentionally not projected yet.
            return
        elif region.id in caption_bindings:
            node_id = _make_text_node(
                "FIGURE_CAPTION", region, CONFIDENCE_CAPTION, "layout caption group"
            )
            main_region_id = caption_bindings[region.id]
            if main_region_id in figure_region_nodes:
                relations.append(
                    generated.SemanticRelation(
                        id=stable_uuid(layout.id, "rel", len(relations)),
                        type="CAPTION_OF",
                        source=node_id,
                        target=figure_region_nodes[main_region_id],
                        confidence=CONFIDENCE_CAPTION,
                        provenanceIds=[],
                    )
                )
        elif region.kind == "TEXT" and label == "HEADING_LIKE":
            _make_text_node(
                "HEADING",
                region,
                CONFIDENCE_HEADING,
                "layout heading label",
                attributes={"level": 1},
            )
        elif region.kind == "TEXT" and region_texts.get(region.id, "").strip():
            _make_text_node("PARAGRAPH", region, CONFIDENCE_PARAGRAPH, "layout text region")

    for region_id in layout.primaryFlow:
        if region_id in regions_by_id:
            _region_for_flow(region_id)

    # Footnotes: layout keeps them out of the primary flow; they appear as
    # FOOTNOTE nodes after the main content (FOOTNOTE_OF relations come
    # with reference recovery, M4).
    for region in layout.regions:
        if region.kind == "FOOTNOTE" and region_texts.get(region.id, "").strip():
            _make_text_node("FOOTNOTE", region, CONFIDENCE_FOOTNOTE, "layout footnote region")

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
