"""M5 RenderComposer: SemanticDocument + TranslationLayer -> RenderDocument."""

from __future__ import annotations

from typing import cast

from document_model.generated import schema_models as generated
from document_model.tree import walk_semantic_nodes

from pdf_pipeline.ids import stable_uuid
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
_PRODUCER = "pdf-pipeline.render-composer"


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
    issues: list[generated.Issue] = []
    bibliography_entries: list[generated.BibliographyEntryContent] = []
    bibliography_block_id: str | None = None

    for node in walk_semantic_nodes(semantic):
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
        node_blocks = _blocks_for_node(
            node,
            content,
            block_id=block_id,
            caption=caption,
            caption_id=caption_id,
            resources=resource_store,
        )
        issues.extend(
            _policy_issues_for_blocks(semantic.id, policy, node, node_blocks, caption is not None)
        )
        blocks.extend(node_blocks)

    if bibliography_entries and bibliography_block_id is not None:
        blocks.append(
            generated.RenderBibliographyBlock(
                renderKind="BIBLIOGRAPHY",
                id=bibliography_block_id,
                entries=bibliography_entries,
            )
        )

    document = generated.RenderDocument(
        schemaVersion="0.2.0",
        id=stable_uuid(semantic.id, "render-document", translation.id),
        semanticDocumentId=semantic.id,
        translationLayerId=translation.id,
        profile=profile,
        policy=policy,
        blocks=blocks,
        provenanceIds=[],
    )
    if issues:
        return document.model_copy(update={"issues": generated.IssueStore(issues=issues)})
    return document


def _blocks_for_node(
    node: generated.SemanticNode,
    content: generated.NodeContent,
    *,
    block_id: str,
    caption: generated.RichText | None,
    caption_id: str | None,
    resources: generated.ResourceStore,
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
            block = generated.RenderTableBlock(
                renderKind="TABLE",
                id=block_id,
                semanticNodeIds=semantic_node_ids,
                table=table_content,
                columnAlignments=alignments,
            )
            if caption is not None:
                block = block.model_copy(update={"caption": caption})
            return [block]
    if node.kind == "EQUATION":
        equation_content = (
            content if isinstance(content, generated.EquationContent) else node.content
        )
        if isinstance(equation_content, generated.EquationContent):
            return [
                generated.RenderEquationBlock(
                    renderKind="EQUATION",
                    id=block_id,
                    semanticNodeIds=[node.id],
                    equation=equation_content,
                )
            ]
    if node.kind == "FIGURE" and isinstance(node.content, generated.FigureContent):
        semantic_node_ids = [node.id]
        if caption is not None and caption_id is not None:
            semantic_node_ids.append(caption_id)
        available = {record.id for record in resources.resources if record.kind == "EMBEDDED_IMAGE"}
        resource_ids = [rid for rid in figure_resource_ids(node.content) if rid in available]
        block = generated.RenderFigureBlock(
            renderKind="FIGURE",
            id=block_id,
            semanticNodeIds=semantic_node_ids,
            figure=node.content,
        )
        if caption is not None:
            block = block.model_copy(update={"caption": caption})
        if resource_ids:
            block = block.model_copy(update={"resourceIds": resource_ids})
        return [block]
    return []


def _policy_issues_for_blocks(
    document_id: str,
    policy: generated.RenderPolicy,
    node: generated.SemanticNode,
    blocks: list[generated.RenderBlock],
    has_caption: bool,
) -> list[generated.Issue]:
    issues: list[generated.Issue] = []
    for block in blocks:
        if block.renderKind == "FIGURE":
            resource_ids = list(block.resourceIds or [])
            if len(resource_ids) > 1:
                issues.append(
                    _render_issue(
                        document_id,
                        "multi-figure-layout",
                        node.id,
                        "figure has multiple bound images; original subfigure "
                        "layout was not restored, so images are stacked",
                        resource_ids,
                        fallback="stacked includegraphics",
                    )
                )
            if has_caption and policy.captionPosition == "SOURCE":
                issues.append(
                    _render_issue(
                        document_id,
                        "caption-source-figure",
                        node.id,
                        "captionPosition=SOURCE approximated as BELOW; "
                        "source caption side is not in Render IR",
                        [node.id],
                        fallback="BELOW",
                    )
                )
        if block.renderKind == "TABLE" and has_caption and policy.captionPosition == "SOURCE":
            issues.append(
                _render_issue(
                    document_id,
                    "caption-source-table",
                    node.id,
                    "captionPosition=SOURCE approximated as ABOVE; "
                    "source caption side is not in Render IR",
                    [node.id],
                    fallback="ABOVE",
                )
            )
        if block.renderKind == "EQUATION" and policy.longEquationHandling == "MULTILINE":
            issues.append(
                _render_issue(
                    document_id,
                    "equation-multiline",
                    node.id,
                    "longEquationHandling=MULTILINE has no break points in Render IR; "
                    "falling back to SCALE_DOWN",
                    [node.id],
                    fallback="SCALE_DOWN",
                )
            )
    return issues


def _render_issue(
    document_id: str,
    token: str,
    node_id: str,
    message: str,
    affected: list[str],
    *,
    fallback: str,
) -> generated.Issue:
    return generated.Issue(
        id=stable_uuid(document_id, "issue", "render", token, node_id),
        category="RENDERING",
        severity="WARNING",
        producer=_PRODUCER,
        message=message,
        affectedIds=affected,
        recoverable=True,
        fallback=fallback,
    )


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
