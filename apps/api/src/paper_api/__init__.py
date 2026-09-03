"""HTTP API runtime. Keep this package free of reusable business logic."""

from __future__ import annotations

__all__ = ["health"]


def health() -> dict[str, str]:
    """Return process liveness metadata for local and CI smoke checks."""
    return {"status": "ok", "service": "api"}
