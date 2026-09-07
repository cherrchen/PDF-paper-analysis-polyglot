"""Provider configuration from environment (FR-PROVIDER-003)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProviderConfig:
    endpoint: str
    api_key: str | None
    model: str
    timeout_s: float = 60.0
    max_retries: int = 2


@dataclass(frozen=True)
class TranslationConfig:
    target_locale: str
    source_locale: str | None
    terminology_file: Path | None
    cache_dir: Path | None
    provider: ProviderConfig | None


def load_translation_config() -> TranslationConfig:
    terminology_path = os.environ.get("PAPER_TERMINOLOGY_FILE")
    cache_dir = os.environ.get("PAPER_TRANSLATION_CACHE_DIR")
    endpoint = os.environ.get("PAPER_LLM_ENDPOINT", "").strip()
    provider = None
    if endpoint:
        provider = ProviderConfig(
            endpoint=endpoint.rstrip("/"),
            api_key=os.environ.get("PAPER_LLM_API_KEY"),
            model=os.environ.get("PAPER_LLM_MODEL", "gpt-4o-mini"),
            timeout_s=float(os.environ.get("PAPER_LLM_TIMEOUT_S", "60")),
            max_retries=int(os.environ.get("PAPER_LLM_MAX_RETRIES", "2")),
        )
    return TranslationConfig(
        target_locale=os.environ.get("PAPER_TARGET_LOCALE", "zh-CN"),
        source_locale=os.environ.get("PAPER_SOURCE_LOCALE"),
        terminology_file=Path(terminology_path) if terminology_path else None,
        cache_dir=Path(cache_dir) if cache_dir else None,
        provider=provider,
    )
