"""M5 RenderComposer: SemanticDocument + TranslationLayer -> RenderDocument."""

from __future__ import annotations

from typing import Any, cast

from document_model.generated import schema_models as generated

from pdf_pipeline.ids import stable_uuid
from pdf_pipeline.math_latex import equation_to_latex
from pdf_pipeline.resource_store import figure_resource_ids

DEFAULT_PROFILE = generated.RenderProfile(
    name="readable-single-column",
    columns=1,
    paperSize="A4",
    fontSizePt=11.0,
    lineSpacingFactor=1.25,
)

DEFAULT_POLICY = generated.RenderPolicy(
    floatFigures=True,
    floatTables=True,
    wideFigureHandling="SCALE_DOWN",
    tableOverflowHandling="SCALE_FONT",
    longEquationHandling="SCALE_DOWN",
    captionPosition="BELOW",
)

_PARAGRAPH_KINDS = {
    "PARAGRAPH",
    "FIGURE_CAPTION",
    "TABLE_CAPTION",
    "FOOTNOTE",
}


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


def compose_render_document(
    semantic: generated.SemanticDocument,
    translation: generated.TranslationLayer,
    *,
    profile: generated.RenderProfile | None = None,
    policy: generated.RenderPolicy | None = None,
    resources: generated.ResourceStore | None = None,
) -> generated.RenderDocument:
    """Compose Render IR without mutating source semantics."""
    if translation.semanticDocumentId != semantic.id:
        raise ValueError("translation layer references a different SemanticDocument")

    profile = profile or DEFAULT_PROFILE
    policy = policy or DEFAULT_POLICY
    resource_store = resources or generated.ResourceStore(resources=[])

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
    bound_figure_caption_ids = {
        caption.id
        for host_id, caption in caption_by_host.items()
        if nodes_by_id[host_id].kind == "FIGURE"
    }
    bound_table_caption_ids = {
        caption.id
        for host_id, caption in caption_by_host.items()
        if nodes_by_id[host_id].kind == "TABLE"
    }

    blocks: list[generated.RenderBlock] = []
    figure_index = 0
    bibliography_entries: list[generated.BibliographyEntryContent] = []
    bibliography_block_id: str | None = None

    for node in _walk_nodes(semantic):
        if node.id in bound_figure_caption_ids or node.id in bound_table_caption_ids:
            continue
        content = translations.get(node.id, node.content)

        if node.kind == "BIBLIOGRAPHY_ENTRY" and isinstance(content, generated.RichText):
            bibliography_block_id = bibliography_block_id or stable_uuid(
                semantic.id, "render-block", "bibliography"
            )
            bibliography_entries.append(
                generated.BibliographyEntryContent(semanticNodeId=node.id, content=content)
            )
            continue

        if bibliography_entries and bibliography_block_id is not None:
            blocks.append(
                generated.RenderBibliographyBlock(
                    renderKind="BIBLIOGRAPHY",
                    id=bibliography_block_id,
                    entries=bibliography_entries,
                )
            )
            bibliography_entries = []
            bibliography_block_id = None

        caption_node = caption_by_host.get(node.id)
        caption: generated.RichText | None = None
        caption_id: str | None = None
        if caption_node is not None:
            translated_caption = translations.get(caption_node.id, caption_node.content)
            if isinstance(translated_caption, generated.RichText):
                caption = translated_caption
                caption_id = caption_node.id

        block_id = stable_uuid(semantic.id, "render-block", node.id)
        blocks.extend(
            _blocks_for_node(
                node,
                content,
                block_id=block_id,
                caption=caption,
                caption_id=caption_id,
                policy=policy,
                resources=resource_store,
                figure_index=figure_index,
            )
        )
        if node.kind == "FIGURE":
            figure_index += 1

    if bibliography_entries and bibliography_block_id is not None:
        blocks.append(
            generated.RenderBibliographyBlock(
                renderKind="BIBLIOGRAPHY",
                id=bibliography_block_id,
                entries=bibliography_entries,
            )
        )

    return generated.RenderDocument(
        schemaVersion="0.2.0",
        id=stable_uuid(semantic.id, "render-document", translation.id),
        semanticDocumentId=semantic.id,
        translationLayerId=translation.id,
        profile=profile,
        policy=policy,
        blocks=blocks,
        provenanceIds=[],
    )


def _blocks_for_node(
    node: generated.SemanticNode,
    content: generated.NodeContent,
    *,
    block_id: str,
    caption: generated.RichText | None,
    caption_id: str | None,
    policy: generated.RenderPolicy,
    resources: generated.ResourceStore,
    figure_index: int,
) -> list[generated.RenderBlock]:
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
    if node.kind == "TABLE":
        table_content = content if isinstance(content, generated.TableContent) else node.content
        if isinstance(table_content, generated.TableContent):
            alignments = _default_column_alignments(table_content.columns)
            semantic_node_ids = [node.id]
            if caption is not None and caption_id is not None:
                semantic_node_ids.append(caption_id)
            table_kwargs: dict[str, Any] = {
                "renderKind": "TABLE",
                "id": block_id,
                "semanticNodeIds": semantic_node_ids,
                "table": table_content,
                "columnAlignments": alignments,
            }
            if caption is not None:
                table_kwargs["caption"] = caption
            return cast(
                "list[generated.RenderBlock]",
                [generated.RenderTableBlock(**table_kwargs)],
            )
    if node.kind == "EQUATION":
        equation_content = (
            content if isinstance(content, generated.EquationContent) else node.content
        )
        if isinstance(equation_content, generated.EquationContent):
            latex = equation_to_latex(equation_content)
            equation = equation_content.model_copy(update={"latex": latex})
            return [
                generated.RenderEquationBlock(
                    renderKind="EQUATION",
                    id=block_id,
                    semanticNodeIds=[node.id],
                    equation=equation,
                )
            ]
    if node.kind == "FIGURE" and isinstance(node.content, generated.FigureContent):
        semantic_node_ids = [node.id]
        if caption is not None and caption_id is not None:
            semantic_node_ids.append(caption_id)
        resource_ids = figure_resource_ids(node.content, resources, figure_index=figure_index)
        figure_kwargs: dict[str, Any] = {
            "renderKind": "FIGURE",
            "id": block_id,
            "semanticNodeIds": semantic_node_ids,
            "figure": node.content,
        }
        if caption is not None:
            figure_kwargs["caption"] = caption
        block = generated.RenderFigureBlock(**figure_kwargs)
        if resource_ids:
            block = block.model_copy(update={"resourceIds": resource_ids})
        return [block]
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


def _default_column_alignments(columns: int) -> list[generated.ColumnAlignment]:
    alignments: list[generated.ColumnAlignment] = ["LEFT"]
    alignments.extend(cast("list[generated.ColumnAlignment]", ["CENTER"] * max(columns - 1, 0)))
    return alignments
