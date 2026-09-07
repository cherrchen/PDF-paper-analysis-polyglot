"""Build structured translation context from a SemanticDocument."""

from __future__ import annotations

from document_model.generated import schema_models as generated

from paper_llm.types import TranslationContext

_CONTEXT_KINDS = frozenset({"HEADING", "PARAGRAPH", "FIGURE_CAPTION", "TABLE_CAPTION", "FOOTNOTE"})
_NEIGHBOR_WINDOW = 240


def build_translation_contexts(
    semantic: generated.SemanticDocument,
    *,
    target_locale: str,
    source_locale: str | None = None,
) -> dict[str, TranslationContext]:
    """Return per-node translation context keyed by semantic node id."""
    nodes_by_id = {node.id: node for node in semantic.nodes}
    ordered = _walk_nodes(semantic, nodes_by_id)
    document_title = _document_title(ordered, nodes_by_id)
    section_titles: list[str] = []
    neighbor_texts: list[str] = []
    contexts: dict[str, TranslationContext] = {}

    for index, node in enumerate(ordered):
        if node.kind == "HEADING":
            text = _rich_text(node.content)
            if text:
                level = node.attributes.get("level")
                if not isinstance(level, int) or level < 1:
                    level = 1
                while len(section_titles) >= level:
                    section_titles.pop()
                section_titles.append(text)

        if node.kind not in _CONTEXT_KINDS and node.kind != "TABLE":
            continue

        preceding = _neighbor_snippet(neighbor_texts, backward=True)
        following_texts = [
            text
            for item in ordered[index + 1 :]
            for text in [_rich_text(item.content)]
            if text and item.kind in _CONTEXT_KINDS
        ]
        following = _neighbor_snippet(following_texts, backward=False)
        contexts[node.id] = TranslationContext(
            target_locale=target_locale,
            source_locale=source_locale,
            document_title=document_title,
            section_path=tuple(section_titles),
            preceding_text=preceding,
            following_text=following,
        )

        if node.kind in _CONTEXT_KINDS:
            text = _rich_text(node.content)
            if text:
                neighbor_texts.append(text)

    return contexts


def _walk_nodes(
    semantic: generated.SemanticDocument,
    nodes_by_id: dict[str, generated.SemanticNode],
) -> list[generated.SemanticNode]:
    ordered: list[generated.SemanticNode] = []
    seen: set[str] = set()

    def walk(node_id: str) -> None:
        if node_id in seen:
            return
        seen.add(node_id)
        node = nodes_by_id.get(node_id)
        if node is None:
            return
        for child_id in node.children:
            if child_id in seen:
                continue
            child = nodes_by_id.get(child_id)
            if child is None:
                continue
            ordered.append(child)
            walk(child.id)

    walk(semantic.rootId)
    return ordered


def _document_title(
    ordered: list[generated.SemanticNode],
    nodes_by_id: dict[str, generated.SemanticNode],
) -> str | None:
    for node in ordered:
        if node.kind == "FRONT_MATTER":
            text = _rich_text(node.content)
            if text:
                return text
        if node.kind == "HEADING":
            text = _rich_text(node.content)
            if text:
                return text
        if node.kind == "PARAGRAPH" and node.parentId:
            parent = nodes_by_id.get(node.parentId)
            if parent is not None and parent.kind == "FRONT_MATTER":
                return _rich_text(node.content)
    return None


def _rich_text(content: generated.NodeContent) -> str | None:
    if isinstance(content, generated.RichText):
        return content.text
    return None


def _neighbor_snippet(texts: list[str], *, backward: bool) -> str | None:
    collected: list[str] = []
    items = reversed(texts) if backward else texts
    for text in items:
        stripped = text.strip()
        if not stripped:
            continue
        collected.append(stripped)
        if sum(len(part) for part in collected) >= _NEIGHBOR_WINDOW:
            break
    if not collected:
        return None
    snippet = " ".join(reversed(collected) if backward else collected)
    if len(snippet) > _NEIGHBOR_WINDOW:
        return snippet[-_NEIGHBOR_WINDOW:] if backward else snippet[:_NEIGHBOR_WINDOW]
    return snippet
