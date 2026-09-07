"""LLM helpers. Product integrations are not implemented yet."""

from __future__ import annotations

from paper_llm.context import build_translation_contexts
from paper_llm.translation import (
    TRANSLATION_MARKER,
    DummyTranslationProvider,
    translate_document,
    translate_rich_text,
)
from paper_llm.types import (
    TranslationContext,
    TranslationProvider,
    TranslationRequest,
    TranslationResult,
)

__all__ = [
    "TRANSLATION_MARKER",
    "DummyTranslationProvider",
    "TranslationContext",
    "TranslationProvider",
    "TranslationRequest",
    "TranslationResult",
    "build_translation_contexts",
    "provider_status",
    "translate_document",
    "translate_rich_text",
]


def provider_status() -> str:
    """Return bootstrap liveness for workspace validation."""
    return "ok"
