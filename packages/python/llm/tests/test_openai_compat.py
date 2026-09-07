"""Tests for OpenAI-compatible provider."""

# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportPrivateUsage=false

from __future__ import annotations

import pytest
from document_model.generated import schema_models as generated
from paper_llm.config import ProviderConfig
from paper_llm.openai_compat import OpenAICompatProvider
from paper_llm.types import TranslationContext, TranslationRequest


def _provider(
    post_json: object,
    *,
    endpoint: str = "http://mock.local",
    model: str = "mock-model",
) -> OpenAICompatProvider:
    return OpenAICompatProvider(
        ProviderConfig(endpoint=endpoint, api_key="test", model=model),
        post_json=post_json,  # type: ignore[arg-type]
    )


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

    provider = _provider(post_json)
    result = provider.translate_request(
        TranslationRequest(
            text="Original paragraph.",
            context=TranslationContext(target_locale="zh-CN"),
        )
    )
    assert result.text == "Translated paragraph."


@pytest.mark.unit
def test_openai_compat_provider_sends_protected_placeholders() -> None:
    captured: dict[str, str] = {}

    def post_json(
        url: str, payload: dict[str, object], headers: dict[str, str]
    ) -> dict[str, object]:
        del url, headers
        messages = payload["messages"]
        assert isinstance(messages, list)
        user = messages[1]
        assert isinstance(user, dict)
        content = user["content"]
        assert isinstance(content, str)
        captured["prompt"] = content
        assert "See [1]." not in content
        assert "⟦0⟧" in content
        return {"choices": [{"message": {"content": "参见 ⟦0⟧。"}}]}

    mark = generated.InlineMark(
        type="CITATION", start=4, end=7, targetNodeId="entry-1", label="[1]"
    )
    result = _provider(post_json).translate_request(
        TranslationRequest(
            text="See [1].",
            marks=[mark],
            context=TranslationContext(target_locale="zh-CN"),
        )
    )
    assert "⟦0⟧" in captured["prompt"]
    assert result.text == "参见 [1]。"
    assert len(result.marks) == 1
    assert result.text[result.marks[0].start : result.marks[0].end] == "[1]"


@pytest.mark.unit
def test_openai_compat_provider_rejects_dropped_placeholders() -> None:
    def post_json(
        url: str, payload: dict[str, object], headers: dict[str, str]
    ) -> dict[str, object]:
        del url, payload, headers
        return {"choices": [{"message": {"content": "参见 [1]。"}}]}

    mark = generated.InlineMark(
        type="CITATION", start=4, end=7, targetNodeId="entry-1", label="[1]"
    )
    provider = _provider(post_json)
    with pytest.raises(RuntimeError, match="dropped protected placeholders"):
        provider.translate_request(
            TranslationRequest(
                text="See [1].",
                marks=[mark],
                context=TranslationContext(target_locale="zh-CN"),
            )
        )


@pytest.mark.unit
def test_create_provider_uses_explicit_config(monkeypatch: pytest.MonkeyPatch) -> None:
    from paper_llm.translation import create_provider

    monkeypatch.setenv("PAPER_LLM_ENDPOINT", "http://from-env.example")
    monkeypatch.setenv("PAPER_LLM_MODEL", "env-model")
    captured: dict[str, str] = {}

    def post_json(
        url: str, payload: dict[str, object], headers: dict[str, str]
    ) -> dict[str, object]:
        captured["url"] = url
        model = payload.get("model")
        captured["model"] = model if isinstance(model, str) else ""
        return {"choices": [{"message": {"content": "ok"}}]}

    provider = create_provider(
        provider_model="openai-compat",
        provider_config=ProviderConfig(
            endpoint="http://from-config.example",
            api_key="k",
            model="config-model",
        ),
    )
    assert isinstance(provider, OpenAICompatProvider)
    provider._post_json = post_json
    provider.translate_request(TranslationRequest(text="hello"))
    assert captured["url"].startswith("http://from-config.example/")
    assert captured["model"] == "config-model"


@pytest.mark.unit
def test_openai_compat_provider_requires_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    from paper_llm.translation import create_provider

    monkeypatch.delenv("PAPER_LLM_ENDPOINT", raising=False)
    with pytest.raises(RuntimeError):
        create_provider(provider_model="openai-compat")
