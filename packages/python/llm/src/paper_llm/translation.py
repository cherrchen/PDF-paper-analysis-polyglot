"""Phase 2.4 dummy translation layer.

Minimal TranslationLayer implementation: prefixes every translatable entry
with ``[TRANSLATED]`` while leaving SemanticDocument untouched.
"""

from __future__ import annotations

from typing import Protocol

from document_model import stable_uuid
from document_model.generated import schema_models as generated

TRANSLATION_MARKER = "[TRANSLATED]"

# Node kinds whose text content is translated in the Walking Skeleton.
TEXT_NODE_KINDS = frozenset({"HEADING", "PARAGRAPH", "FIGURE_CAPTION", "TABLE_CAPTION"})


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
) -> generated.TranslationLayer:
    """Build an independent dummy TranslationLayer for ``semantic``.

    SemanticDocument remains untouched. Entries reference stable node IDs and
    contain only locale-specific generated content.
    """
    provider = provider or DummyTranslationProvider()
    entries: list[generated.TranslationEntry] = []
    for node in semantic.nodes:
        text = getattr(node.content, "text", None)
        if node.kind in TEXT_NODE_KINDS and isinstance(text, str):
            content = node.content.model_copy(update={"text": provider.translate(text)})
            entries.append(
                generated.TranslationEntry(
                    semanticNodeId=node.id,
                    content=content,
                    confidence=1.0,
                    provenanceIds=[],
                )
            )
    target_locale = "und-x-dummy"
    return generated.TranslationLayer(
        schemaVersion="0.1.0",
        id=stable_uuid(semantic.id, "translation-layer", target_locale),
        semanticDocumentId=semantic.id,
        targetLocale=target_locale,
        entries=entries,
        provenanceIds=[],
    )
