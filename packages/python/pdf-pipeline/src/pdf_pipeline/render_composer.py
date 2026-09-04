"""M2 RenderComposer: SemanticDocument + TranslationLayer -> RenderDocument."""

from __future__ import annotations

from document_model.generated import schema_models as generated

from pdf_pipeline.ids import stable_uuid


def _walk_nodes(semantic: generated.SemanticDocument) -> list[generated.SemanticNode]:
    by_id = {node.id: node for node in semantic.nodes}
    ordered: list[generated.SemanticNode] = []

    def walk(node_id: str) -> None:
        node = by_id[node_id]
        for child_id in node.children:
            child = by_id[child_id]
            ordered.append(child)
            walk(child.id)

    walk(semantic.rootId)
    return ordered


def compose_render_document(
    semantic: generated.SemanticDocument,
    translation: generated.TranslationLayer,
) -> generated.RenderDocument:
    """Compose the minimal generic-academic Render IR without mutating source semantics."""
    if translation.semanticDocumentId != semantic.id:
        raise ValueError("translation layer references a different SemanticDocument")

    nodes_by_id = {node.id: node for node in semantic.nodes}
    translations: dict[str, generated.NodeContent] = {}
    for entry in translation.entries:
        if entry.semanticNodeId not in nodes_by_id:
            raise ValueError(f"translation entry references unknown node {entry.semanticNodeId}")
        if entry.semanticNodeId in translations:
            raise ValueError(f"duplicate translation entry for node {entry.semanticNodeId}")
        translations[entry.semanticNodeId] = entry.content
    caption_by_figure = {
        relation.target: nodes_by_id[relation.source]
        for relation in semantic.relations
        if relation.type == "CAPTION_OF"
        and relation.source in nodes_by_id
        and relation.target in nodes_by_id
    }
    bound_caption_ids = {caption.id for caption in caption_by_figure.values()}
    blocks: list[generated.RenderBlock] = []

    for node in _walk_nodes(semantic):
        if node.id in bound_caption_ids:
            continue
        content = translations.get(node.id, node.content)
        block_id = stable_uuid(semantic.id, "render-block", node.id)
        if node.kind == "HEADING" and isinstance(content, generated.RichText):
            level = node.attributes.get("level")
            blocks.append(
                generated.RenderHeadingBlock(
                    renderKind="HEADING",
                    id=block_id,
                    semanticNodeIds=[node.id],
                    content=content,
                    level=level if isinstance(level, int) and 1 <= level <= 3 else 1,
                )
            )
        elif node.kind in {"PARAGRAPH", "FIGURE_CAPTION"} and isinstance(
            content, generated.RichText
        ):
            blocks.append(
                generated.RenderParagraphBlock(
                    renderKind="PARAGRAPH",
                    id=block_id,
                    semanticNodeIds=[node.id],
                    content=content,
                )
            )
        elif node.kind == "FIGURE" and isinstance(node.content, generated.FigureContent):
            caption_node = caption_by_figure.get(node.id)
            caption = None
            semantic_node_ids = [node.id]
            if caption_node is not None:
                translated_caption = translations.get(caption_node.id, caption_node.content)
                if isinstance(translated_caption, generated.RichText):
                    caption = translated_caption
                    semantic_node_ids.append(caption_node.id)
            blocks.append(
                generated.RenderFigureBlock(
                    renderKind="FIGURE",
                    id=block_id,
                    semanticNodeIds=semantic_node_ids,
                    figure=node.content,
                    caption=caption,
                )
            )

    return generated.RenderDocument(
        schemaVersion="0.1.0",
        id=stable_uuid(semantic.id, "render-document", translation.id),
        semanticDocumentId=semantic.id,
        translationLayerId=translation.id,
        profile=generated.RenderProfile(name="generic-academic"),
        policy=generated.RenderPolicy(floatFigures=True),
        blocks=blocks,
        provenanceIds=[],
    )
