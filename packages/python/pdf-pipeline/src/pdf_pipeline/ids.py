"""Deterministic opaque-ID derivation shared by pipeline stages.

Canonical IDs must match the schema's ULID/UUID pattern. Stages derive them
from the source fingerprint plus stable local counters so parsing the same
PDF bytes twice yields identical documents.
"""

from __future__ import annotations

import hashlib


def stable_uuid(fingerprint: str, kind: str, *parts: object) -> str:
    """UUID-shaped deterministic ID from source bytes and stable parts."""
    digest = hashlib.sha256(
        "\x1f".join((fingerprint, kind, *(str(part) for part in parts))).encode()
    ).hexdigest()
    return f"{digest[0:8]}-{digest[8:12]}-{digest[12:16]}-{digest[16:20]}-{digest[20:32]}"
