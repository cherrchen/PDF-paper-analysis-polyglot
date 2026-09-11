# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false
"""Untyped HTTP JSON boundary for OpenAI-compatible responses."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import httpx


def read_json_object(response: httpx.Response) -> dict[str, object]:
    payload = response.json()
    if not isinstance(payload, dict):
        raise TypeError("provider returned non-object JSON")
    return {str(key): value for key, value in payload.items()}


def chat_completion_text(data: dict[str, object]) -> str:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError("provider returned no choices")
    first = choices[0]
    if not isinstance(first, dict):
        raise TypeError("provider returned no choices")
    message = first.get("message")
    if not isinstance(message, dict):
        raise TypeError("provider returned empty content")
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("provider returned empty content")
    return content.strip()
