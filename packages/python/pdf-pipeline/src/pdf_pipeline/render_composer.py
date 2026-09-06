"""M2 RenderComposer: SemanticDocument + TranslationLayer -> RenderDocument.

M4 additions: TABLE and EQUATION nodes must not silently vanish from the
target. Until the real render engine (M5) typesets them, they project to
paragraph text carrying every cell / the raw formula, and bibliography
entries render as paragraphs. Container kinds (SECTION / FRONT_MATTER /
BIBLIOGRAPHY) hold no text of their own; their children walk through.
"""

from __future__ import annotations

from document_model.generated import schema_models as generated

from pdf_pipeline.ids import stable_uuid


def _walk_nodes(semantic: generated.SemanticDocument) -> list[generated.SemanticNode]:
    by_id = {node.id: node for node in semantic.nodes}
    ordered: list[generated.SemanticNode] = []
    seen: set[str] = set()

    def walk(node_id: str) -> None:
        if node_id in seen:
            return
        seen.add(node_id)
        node = by_id.get(node_id)
        if node is None:
            return
        for child_id in node.children:
            if child_id in seen:
                continue
            child = by_id.get(child_id)
            if child is None:
                continue
            ordered.append(child)
            walk(child.id)

    walk(semantic.rootId)
    return ordered


def _table_text(content: generated.TableContent) -> generated.RichText:
    """Row-major plain text for a table (M5 replaces this with real tables)."""
    rows: dict[int, list[str]] = {}
    for cell in content.cells:
        rows.setdefault(cell.row, []).append(cell.content.text)
    lines = [" | ".join(rows[row]) for row in sorted(rows)]
    return generated.RichText(text="\n".join(lines), marks=[])


def _equation_text(content: generated.EquationContent) -> generated.RichText:
    """Plain text for an equation: best representation plus its number."""
    body = content.unicodeText or content.rawText or ""
    text = f"{body} ({content.number})" if content.number else body
    return generated.RichText(text=text, marks=[])


_PARAGRAPH_KINDS = {
    "PARAGRAPH",
    "FIGURE_CAPTION",
    "TABLE_CAPTION",
    "FOOTNOTE",
    "BIBLIOGRAPHY_ENTRY",
}


def _blocks_for_node(
    node: generated.SemanticNode,
    content: generated.NodeContent,
    *,
    block_id: str,
    caption: generated.RichText | None,
    caption_id: str | None,
) -> list[generated.RenderBlock]:
    """Project one semantic node to zero or one render block."""
    if node.kind == "HEADING" and isinstance(content, generated.RichText):
        level = node.attributes.get("level")
        return [
            generated.RenderHeadingBlock(
                renderKind="HEADING",
                id=block_id,
                semanticNodeIds=[node.id],
                content=content,
                level=level if isinstance(level, int) and 1 <= level <= 3 else 1,
            )
        ]
    if node.kind in _PARAGRAPH_KINDS and isinstance(content, generated.RichText):
        return [_paragraph(block_id, node.id, content)]
    if node.kind == "TABLE" and isinstance(node.content, generated.TableContent):
        # M5 renders real tables; until then project every cell so no
        # table content is ever silently dropped from the target.
        return [_paragraph(block_id, node.id, _table_text(node.content))]
    if node.kind == "EQUATION" and isinstance(node.content, generated.EquationContent):
        return [_paragraph(block_id, node.id, _equation_text(node.content))]
    if node.kind == "FIGURE" and isinstance(node.content, generated.FigureContent):
        semantic_node_ids = [node.id]
        if caption is not None and caption_id is not None:
            semantic_node_ids.append(caption_id)
        return [
            generated.RenderFigureBlock(
                renderKind="FIGURE",
                id=block_id,
                semanticNodeIds=semantic_node_ids,
                figure=node.content,
                caption=caption,
            )
        ]
    return []


def _paragraph(
    block_id: str, node_id: str, content: generated.RichText
) -> generated.RenderParagraphBlock:
    return generated.RenderParagraphBlock(
        renderKind="PARAGRAPH",
        id=block_id,
        semanticNodeIds=[node_id],
        content=content,
    )


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
    caption_by_host = {
        relation.target: nodes_by_id[relation.source]
        for relation in semantic.relations
        if relation.type == "CAPTION_OF"
        and relation.source in nodes_by_id
        and relation.target in nodes_by_id
    }
    # FIGURE blocks consume their caption; TABLE captions emit as their own
    # paragraph so the title is never dropped from the target.
    bound_figure_caption_ids = {
        caption.id
        for host_id, caption in caption_by_host.items()
        if nodes_by_id[host_id].kind == "FIGURE"
    }
    blocks: list[generated.RenderBlock] = []

    for node in _walk_nodes(semantic):
        if node.id in bound_figure_caption_ids:
            continue
        content = translations.get(node.id, node.content)
        caption_node = caption_by_host.get(node.id)
        caption: generated.RichText | None = None
        caption_id: str | None = None
        if caption_node is not None:
            translated_caption = translations.get(caption_node.id, caption_node.content)
            if isinstance(translated_caption, generated.RichText):
                caption = translated_caption
                caption_id = caption_node.id
        blocks.extend(
            _blocks_for_node(
                node,
                content,
                block_id=stable_uuid(semantic.id, "render-block", node.id),
                caption=caption,
                caption_id=caption_id,
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
