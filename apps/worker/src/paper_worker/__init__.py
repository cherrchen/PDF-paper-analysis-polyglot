"""Background worker runtime. Keep this package free of reusable business logic."""

from __future__ import annotations

__all__ = ["status"]


def status() -> dict[str, str]:
    """Return worker liveness metadata for local and CI smoke checks."""
    return {"status": "ok", "service": "worker"}
