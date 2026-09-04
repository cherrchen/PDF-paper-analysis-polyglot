"""Opaque persistent ID generation and canonical schema version."""

from __future__ import annotations

import hashlib
import secrets
import threading
import time

SCHEMA_VERSION = "0.1.0"

# Crockford base32 alphabet (excludes I, L, O, U) used by ULID.
_ENCODING = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_ENCODING_LEN = len(_ENCODING)

_LOCK = threading.Lock()


class _Monotonic:
    """Last emitted 130-bit ULID value, for same-millisecond monotonicity."""

    def __init__(self) -> None:
        self.last = 0


_STATE = _Monotonic()


def _encode(value: int) -> str:
    chars: list[str] = []
    for _ in range(26):
        chars.append(_ENCODING[value % _ENCODING_LEN])
        value //= _ENCODING_LEN
    return "".join(reversed(chars))


def new_id() -> str:
    """Generate a new opaque ULID-style identifier.

    Monotonic across calls (same-millisecond ids keep increasing), which
    keeps IDs sortable by creation time without encoding domain meaning.
    """
    with _LOCK:
        timestamp_ms = time.time_ns() // 1_000_000
        randomness = secrets.token_bytes(10)
        value = (timestamp_ms << 80) | int.from_bytes(randomness, "big")
        if value <= _STATE.last:
            value = _STATE.last + 1
        _STATE.last = value
    return _encode(value)


def stable_uuid(namespace: str, kind: str, *parts: object) -> str:
    """Derive a deterministic UUID-shaped opaque id from stable inputs."""
    digest = hashlib.sha256(
        "\x1f".join((namespace, kind, *(str(part) for part in parts))).encode()
    ).hexdigest()
    return f"{digest[0:8]}-{digest[8:12]}-{digest[12:16]}-{digest[16:20]}-{digest[20:32]}"
