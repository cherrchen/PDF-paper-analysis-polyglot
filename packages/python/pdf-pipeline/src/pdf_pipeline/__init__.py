"""Reusable PDF ingestion, recovery, composition, rendering, and mapping pipeline."""

from __future__ import annotations

__all__ = ["pipeline_status"]


def pipeline_status() -> str:
    """Return bootstrap liveness for workspace validation."""
    return "ok"
