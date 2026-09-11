"""OpenAI-compatible Chat Completions translation adapter (M5 Phase 5.5)."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import httpx

from paper_llm.http_json import chat_completion_text, read_json_object
from paper_llm.prompt import SYSTEM_PROMPT, build_translation_prompt
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
        def complete_protected(protected: str) -> str:
            prompt = build_translation_prompt(request, source_text=protected)
            return self._complete(prompt)

        text, marks = translate_rich_text_body(
            request.text,
            request.marks,
            complete_protected,
        )
        return TranslationResult(text=text, marks=marks, confidence=0.85)

    def _complete(self, prompt: str) -> str:
        payload: dict[str, object] = {
            "model": self._config.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
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
        return chat_completion_text(data)

    def _request(
        self, url: str, payload: dict[str, object], headers: dict[str, str]
    ) -> dict[str, object]:
        if self._post_json is not None:
            return self._post_json(url, payload, headers)
        if self._client is not None:
            return _post_chat_completion(self._client, url, payload, headers)
        with httpx.Client(timeout=self._config.timeout_s) as client:
            return _post_chat_completion(client, url, payload, headers)


def _post_chat_completion(
    client: httpx.Client,
    url: str,
    payload: dict[str, object],
    headers: dict[str, str],
) -> dict[str, object]:
    response = client.post(url, json=payload, headers=headers)
    if response.status_code in {408, 409, 429, 500, 502, 503, 504}:
        raise _RetriableProviderError(response.status_code)
    response.raise_for_status()
    return read_json_object(response)


class _RetriableProviderError(RuntimeError):
    def __init__(self, status_code: int) -> None:
        super().__init__(f"retriable provider error: HTTP {status_code}")
        self.status_code = status_code
