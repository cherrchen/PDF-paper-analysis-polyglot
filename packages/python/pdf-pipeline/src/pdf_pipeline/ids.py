"""Deterministic opaque-ID derivation shared by pipeline stages.

Canonical IDs must match the schema's ULID/UUID pattern. Stages derive them
from the source fingerprint plus stable local counters so parsing the same
PDF bytes twice yields identical documents.
"""

from __future__ import annotations

from document_model import stable_uuid

__all__ = ["stable_uuid"]
