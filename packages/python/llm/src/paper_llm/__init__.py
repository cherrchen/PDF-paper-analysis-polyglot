"""LLM helpers. Product integrations are not implemented yet."""

from __future__ import annotations

__all__ = ["provider_status"]


def provider_status() -> str:
    """Return bootstrap liveness for workspace validation."""
    return "ok"
