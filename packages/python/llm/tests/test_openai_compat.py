"""Tests for OpenAI-compatible provider."""

from __future__ import annotations

import pytest
from paper_llm.config import ProviderConfig
from paper_llm.openai_compat import OpenAICompatProvider
from paper_llm.types import TranslationContext, TranslationRequest


@pytest.mark.unit
def test_openai_compat_provider_uses_mock_response() -> None:
    def post_json(
        url: str, payload: dict[str, object], headers: dict[str, str]
    ) -> dict[str, object]:
        assert url.endswith("/v1/chat/completions")
        return {
            "choices": [
                {"message": {"content": "Translated paragraph."}},
            ]
        }

    provider = OpenAICompatProvider(
        ProviderConfig(endpoint="http://mock.local", api_key="test", model="mock-model"),
        post_json=post_json,
    )
    result = provider.translate_request(
        TranslationRequest(
            text="Original paragraph.",
            context=TranslationContext(target_locale="zh-CN"),
        )
    )
    assert result.text == "Translated paragraph."


@pytest.mark.unit
@pytest.mark.slow
def test_openai_compat_provider_requires_endpoint() -> None:
    from paper_llm.translation import create_provider

    with pytest.raises(RuntimeError):
        create_provider(provider_model="openai-compat")
