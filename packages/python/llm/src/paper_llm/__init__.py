"""LLM helpers. Product integrations are not implemented yet."""

from __future__ import annotations

from paper_llm.translation import (
    TRANSLATION_MARKER,
    DummyTranslationProvider,
    TranslationContext,
    TranslationProvider,
    TranslationRequest,
    TranslationResult,
    translate_document,
    translate_rich_text,
)

__all__ = [
    "TRANSLATION_MARKER",
    "DummyTranslationProvider",
    "TranslationContext",
    "TranslationProvider",
    "TranslationRequest",
    "TranslationResult",
    "provider_status",
    "translate_document",
    "translate_rich_text",
]


def provider_status() -> str:
    """Return bootstrap liveness for workspace validation."""
    return "ok"
