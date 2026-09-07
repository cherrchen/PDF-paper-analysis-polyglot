# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnnecessaryIsInstance=false
"""OpenAI-compatible Chat Completions translation adapter (M5 Phase 5.5)."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import httpx

from paper_llm.translation import translate_rich_text_body
from paper_llm.types import TranslationRequest, TranslationResult

if TYPE_CHECKING:
    from collections.abc import Callable

    from paper_llm.config import ProviderConfig


class OpenAICompatProvider:
    """HTTP adapter for OpenAI-compatible chat completion endpoints."""

    def __init__(
        self,
        config: ProviderConfig,
        *,
        client: httpx.Client | None = None,
        post_json: Callable[[str, dict[str, object], dict[str, str]], dict[str, object]]
        | None = None,
    ) -> None:
        self._config = config
        self._client = client
        self._post_json = post_json

    def translate_request(self, request: TranslationRequest) -> TranslationResult:
        prompt = _build_prompt(request)
        response_text = self._complete(prompt)
        text, marks = translate_rich_text_body(
            request.text,
            request.marks,
            lambda _protected: response_text,
        )
        return TranslationResult(text=text, marks=marks, confidence=0.85)

    def _complete(self, prompt: str) -> str:
        payload: dict[str, object] = {
            "model": self._config.model,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
        }
        headers = {"Content-Type": "application/json"}
        if self._config.api_key:
            headers["Authorization"] = f"Bearer {self._config.api_key}"
        url = f"{self._config.endpoint}/v1/chat/completions"
        attempt = 0
        while True:
            try:
                data = self._request(url, payload, headers)
                break
            except _RetriableProviderError:
                attempt += 1
                if attempt > self._config.max_retries:
                    raise
                time.sleep(min(2**attempt, 8))
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise RuntimeError("provider returned no choices")
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("provider returned empty content")
        return content.strip()

    def _request(
        self, url: str, payload: dict[str, object], headers: dict[str, str]
    ) -> dict[str, object]:
        if self._post_json is not None:
            data = self._post_json(url, payload, headers)
            if not isinstance(data, dict):
                raise RuntimeError("provider mock returned non-object JSON")
            return data
        with self._client or httpx.Client(timeout=self._config.timeout_s) as client:
            response = client.post(url, json=payload, headers=headers)
            if response.status_code in {408, 409, 429, 500, 502, 503, 504}:
                raise _RetriableProviderError(response.status_code)
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                raise TypeError("provider returned non-object JSON")
            return data


class _RetriableProviderError(RuntimeError):
    def __init__(self, status_code: int) -> None:
        super().__init__(f"retriable provider error: HTTP {status_code}")
        self.status_code = status_code


_SYSTEM_PROMPT = (
    "You are an academic paper translator. Preserve placeholder tokens such as "
    "⟦0⟧ exactly. Never translate citation markers, equation references, or "
    "bibliography labels. Return only the translated text."
)


def _build_prompt(request: TranslationRequest) -> str:
    sections: list[str] = []
    context = request.context
    if context.document_title:
        sections.append(f"Document title: {context.document_title}")
    if context.section_path:
        sections.append("Section path: " + " > ".join(context.section_path))
    if context.preceding_text:
        sections.append(f"Previous paragraph: {context.preceding_text}")
    if context.following_text:
        sections.append(f"Next paragraph: {context.following_text}")
    if request.terminology:
        glossary = "\n".join(
            f"- {term.term} => {term.preferredTranslation}" for term in request.terminology
        )
        sections.append(f"Terminology:\n{glossary}")
    sections.append(f"Target locale: {context.target_locale or 'unspecified'}")
    sections.append(f"Source text:\n{request.text}")
    return "\n\n".join(sections)
