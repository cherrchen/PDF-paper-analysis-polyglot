"""Build structured translation context from a SemanticDocument."""

from __future__ import annotations

from document_model.generated import schema_models as generated
from document_model.tree import walk_semantic_nodes

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
    ordered = walk_semantic_nodes(semantic)
    document_title = _document_title(ordered, nodes_by_id)
    neighbor_indexes: list[int] = []
    neighbor_texts: list[str] = []
    for index, node in enumerate(ordered):
        if node.kind not in _CONTEXT_KINDS:
            continue
        text = _rich_text(node.content)
        if not text:
            continue
        neighbor_indexes.append(index)
        neighbor_texts.append(text)

    section_titles: list[str] = []
    contexts: dict[str, TranslationContext] = {}
    neighbor_cursor = 0

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

        while neighbor_cursor < len(neighbor_indexes) and neighbor_indexes[neighbor_cursor] < index:
            neighbor_cursor += 1
        follow_start = neighbor_cursor
        if follow_start < len(neighbor_indexes) and neighbor_indexes[follow_start] == index:
            follow_start += 1
        contexts[node.id] = TranslationContext(
            target_locale=target_locale,
            source_locale=source_locale,
            document_title=document_title,
            section_path=tuple(section_titles),
            preceding_text=_neighbor_snippet_range(
                neighbor_texts, 0, neighbor_cursor, backward=True
            ),
            following_text=_neighbor_snippet_range(
                neighbor_texts, follow_start, len(neighbor_texts), backward=False
            ),
        )

    return contexts


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


def _neighbor_snippet_range(
    texts: list[str], start: int, end: int, *, backward: bool
) -> str | None:
    collected: list[str] = []
    indexes = range(end - 1, start - 1, -1) if backward else range(start, end)
    for index in indexes:
        stripped = texts[index].strip()
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
