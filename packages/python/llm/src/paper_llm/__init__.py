"""LLM helpers. Product integrations are not implemented yet."""

from __future__ import annotations

from paper_llm.cache import TranslationCache
from paper_llm.config import load_translation_config
from paper_llm.context import build_translation_contexts
from paper_llm.translation import (
    DUMMY_PROVIDER_MODEL,
    TRANSLATION_MARKER,
    DummyTranslationProvider,
    TranslationProviderNotConfiguredError,
    create_provider,
    is_dummy_provider_model,
    retranslate_nodes,
    translate_document,
    translate_rich_text,
    translation_requires_provider,
)
from paper_llm.types import (
    TranslationContext,
    TranslationProvider,
    TranslationRequest,
    TranslationResult,
)

__all__ = [
    "DUMMY_PROVIDER_MODEL",
    "TRANSLATION_MARKER",
    "DummyTranslationProvider",
    "TranslationCache",
    "TranslationContext",
    "TranslationProvider",
    "TranslationProviderNotConfiguredError",
    "TranslationRequest",
    "TranslationResult",
    "build_translation_contexts",
    "create_provider",
    "is_dummy_provider_model",
    "load_translation_config",
    "provider_status",
    "retranslate_nodes",
    "translate_document",
    "translate_rich_text",
    "translation_requires_provider",
]


def provider_status() -> str:
    """Return bootstrap liveness for workspace validation."""
    return "ok"
