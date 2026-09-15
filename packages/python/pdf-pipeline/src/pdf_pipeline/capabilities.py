"""Phase 7.2 Capability Registry: which provider owns which capability.

The registry is declarative data (``data/capability-registry.toml``)
mirroring docs/architecture/document-architecture.md §35. Adaptive routing
(Phase 7.3) and evidence fusion (Phase 7.4) consume it to weight provider
evidence by capability authority instead of counting votes.

The registry is loaded with :mod:`tomllib` (stdlib) so the ensemble stays
dependency-free and deterministic. The bundled table stays the default; an
operator may point at an overriding file with the same shape through
``PAPER_CAPABILITY_REGISTRY`` or the pipeline's ``--registry`` flag (M8
batch E). An override is read on every call and its bytes — not its path —
enter the EVIDENCE/LAYOUT stage cache keys, so switching parsers changes
the key and invalidates exactly those stages. A broken override raises
:class:`CapabilityRegistryError` instead of falling back to the bundled
registry: a silent fallback would silently keep the old parser.
"""

from __future__ import annotations

import hashlib
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from types import MappingProxyType
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

REGISTRY_RESOURCE = "capability-registry.toml"


class CapabilityRegistryError(ValueError):
    """The capability registry is unreadable, unparsable, or invalid."""


@dataclass(frozen=True)
class Capability:
    """One capability slot with its provider precedence."""

    name: str
    primary: str
    challenger: str | None = None
    fallback: str | None = None

    def authorities(self) -> tuple[str, ...]:
        """Provider names in authority order (primary first)."""
        return tuple(
            provider
            for provider in (self.primary, self.challenger, self.fallback)
            if provider is not None
        )


# Flattened dotted capability keys -> slot (e.g. "table.structure").
Registry = Mapping[str, Capability]
_UNLISTED_RANK = 3

# Capabilities the recovery engines own outright; no provider may claim them.
_INTERNAL_CAPABILITIES = frozenset(
    {"layout.reading_order", "layout.column_detection", "semantic.document"}
)


def load_registry(path: Path | None = None) -> Registry:
    """Load the capability registry for ``path`` (``None`` = bundled).

    Returns a read-only mapping. Callers that need a mutable copy for a
    test or overlay must ``dict(load_registry())``; mutating the returned
    object must not change later documents.

    The bundled registry is immutable package data and is parsed once per
    process. An overriding ``path`` is read and parsed on every call: the
    operator may edit it at any time, so caching it would route with a stale
    provider selection.
    """
    if path is None:
        return _bundled_registry()
    return _parse_registry(registry_text(path), source=str(path))


def registry_text(path: Path | None = None) -> str:
    """Raw TOML of the effective registry (``None`` = bundled package data).

    Never falls back to the bundled registry when ``path`` is given: a
    fallback would silently route with the default providers while the
    operator believes the override is in effect.
    """
    if path is None:
        return _registry_text()
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise CapabilityRegistryError(f"cannot read capability registry {path}: {error}") from error


@lru_cache(maxsize=1)
def _registry_text() -> str:
    return (
        resources.files("pdf_pipeline")
        .joinpath(f"data/{REGISTRY_RESOURCE}")
        .read_text(encoding="utf-8")
    )


def registry_fingerprint(path: Path | None = None) -> str:
    """Content hash of the effective registry, for stage cache keys.

    A digest rather than a version constant: the registry is hand-edited
    data, so any edit — including one that forgets to bump a version — must
    invalidate the stages that routed providers with it. With an override
    the digest follows the override's bytes, not the bundled ones, so the
    cache key describes the registry a run actually used.
    """
    return hashlib.sha256(registry_text(path).encode("utf-8")).hexdigest()


def resolve_registry(path: Path | None = None) -> tuple[Registry, str]:
    """Parse and fingerprint the effective registry from a single read.

    A run must route with exactly the registry its stage keys describe:
    reading twice would let an edit between the two reads record a digest
    that does not match the artifacts, which is a silent cache hit.
    """
    if path is None:
        return _bundled_registry(), registry_fingerprint()
    text = registry_text(path)
    return _parse_registry(text, source=str(path)), hashlib.sha256(text.encode("utf-8")).hexdigest()


@lru_cache(maxsize=1)
def _bundled_registry() -> Registry:
    return _parse_registry(_registry_text(), source=f"bundled {REGISTRY_RESOURCE}")


def _parse_registry(text: str, *, source: str) -> Registry:
    try:
        raw = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise CapabilityRegistryError(
            f"cannot parse capability registry {source}: {error}"
        ) from error
    parsed: dict[str, Capability] = {}
    for domain, slots in raw.items():
        for slot, providers in slots.items():
            name = f"{domain}.{slot}"
            parsed[name] = Capability(
                name=name,
                primary=providers["primary"],
                challenger=providers.get("challenger"),
                fallback=providers.get("fallback"),
            )
    _validate(parsed, source=source)
    return MappingProxyType(parsed)


def _validate(registry: Mapping[str, Capability], *, source: str) -> None:
    """Enforce the architecture invariants on the loaded registry."""
    missing = _INTERNAL_CAPABILITIES - registry.keys()
    if missing:
        raise CapabilityRegistryError(
            f"capability registry {source} misses internal capabilities: {sorted(missing)}"
        )
    for name in _INTERNAL_CAPABILITIES:
        if registry[name].primary != "internal":
            raise CapabilityRegistryError(
                f"capability registry {source}: capability {name} must stay "
                "internal-owned (architecture §35)"
            )
    for capability in registry.values():
        owners = [
            provider
            for provider in (capability.primary, capability.challenger, capability.fallback)
            if provider
        ]
        if len(owners) != len(set(owners)):
            raise CapabilityRegistryError(
                f"capability registry {source}: capability {capability.name} lists a provider twice"
            )


def authority_rank(registry: Registry, capability: str, provider: str) -> int:
    """Authority rank of ``provider`` for ``capability`` (0 = primary).

    Ranks are role slots, not compact indexes: missing challenger or
    fallback does not promote a later provider. Unlisted providers always
    rank ``_UNLISTED_RANK`` (weaker than any named role).
    """
    slot = registry[capability]
    if provider == slot.primary:
        return 0
    if slot.challenger is not None and provider == slot.challenger:
        return 1
    if slot.fallback is not None and provider == slot.fallback:
        return 2
    return _UNLISTED_RANK


def is_authority(registry: Registry, capability: str, provider: str) -> bool:
    """True when the provider is listed as an authority for the capability."""
    return provider in registry[capability].authorities()
