"""Phase 2.4 dummy translation layer.

Minimal TranslationLayer implementation: prefixes every text node with
``[TRANSLATED]``. Verifies that SemanticNode identity is preserved —
translation rewrites content, never IDs.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from document_model.generated import schema_models as generated

TRANSLATION_MARKER = "[TRANSLATED]"

# Node kinds whose text content is translated in the Walking Skeleton.
TEXT_NODE_KINDS = frozenset({"HEADING", "PARAGRAPH", "FIGURE_CAPTION"})


class TranslationProvider(Protocol):
    """Minimal translation interface for the Walking Skeleton."""

    def translate(self, text: str) -> str: ...


class DummyTranslationProvider:
    """Prefixes text with the marker; no real translation happens."""

    def translate(self, text: str) -> str:
        return f"{TRANSLATION_MARKER} {text}"


def translate_document(
    semantic: generated.SemanticDocument,
    provider: TranslationProvider | None = None,
) -> generated.SemanticDocument:
    """Return a translated copy of the semantic document.

    Identity guarantee: node IDs, relations, and tree shape are untouched;
    only the ``text`` of text-bearing nodes changes.
    """
    provider = provider or DummyTranslationProvider()
    nodes: list[generated.SemanticNode] = []
    for node in semantic.nodes:
        text = getattr(node.content, "text", None)
        if node.kind in TEXT_NODE_KINDS and isinstance(text, str):
            content = node.content.model_copy(update={"text": provider.translate(text)})
            nodes.append(node.model_copy(update={"content": content}))
        else:
            nodes.append(node)
    return semantic.model_copy(update={"nodes": nodes})
