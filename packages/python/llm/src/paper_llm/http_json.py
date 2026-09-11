"""JSON object coercion for OpenAI-compatible HTTP responses."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    import httpx


def as_json_object(value: object) -> dict[str, object]:
    """Copy a mapping into ``dict[str, object]``; raise if ``value`` is not a dict."""
    if not isinstance(value, dict):
        raise TypeError("expected JSON object")
    typed: dict[str, object] = {}
    for key, item in value.items():  # pyright: ignore[reportUnknownVariableType, reportUnknownMemberType]
        typed[str(key)] = item  # pyright: ignore[reportUnknownArgumentType]
    return typed


def read_json_object(response: httpx.Response) -> dict[str, object]:
    payload: object = response.json()  # pyright: ignore[reportUnknownMemberType]
    return as_json_object(payload)


def chat_completion_text(data: dict[str, object]) -> str:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError("provider returned no choices")
    try:
        first = as_json_object(cast("object", choices[0]))
    except TypeError as error:
        raise TypeError("provider returned no choices") from error
    try:
        message = as_json_object(first.get("message"))
    except TypeError as error:
        raise TypeError("provider returned empty content") from error
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("provider returned empty content")
    return content.strip()
