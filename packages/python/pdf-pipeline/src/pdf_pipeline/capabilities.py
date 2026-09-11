"""Phase 7.2 Capability Registry: which provider owns which capability.

The registry is declarative data (``data/capability-registry.toml``)
mirroring docs/architecture/document-architecture.md §35. Adaptive routing
(Phase 7.3) and evidence fusion (Phase 7.4) consume it to weight provider
evidence by capability authority instead of counting votes.

The registry is loaded with :mod:`tomllib` (stdlib) so the ensemble stays
dependency-free and deterministic; the same table is meant to move to a
runtime-editable config only if a real deployment needs it (Agent Note:
2026-09-12-m7-parser-ensemble).
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources

REGISTRY_RESOURCE = "capability-registry.toml"


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
Registry = dict[str, Capability]

# Capabilities the recovery engines own outright; no provider may claim them.
_INTERNAL_CAPABILITIES = frozenset(
    {"layout.reading_order", "layout.column_detection", "semantic.document"}
)


def load_registry() -> Registry:
    """Load the bundled capability registry deterministically."""
    return _load_registry_impl()


@lru_cache(maxsize=1)
def _load_registry_impl() -> Registry:
    text = (
        resources.files("pdf_pipeline")
        .joinpath(f"data/{REGISTRY_RESOURCE}")
        .read_text(encoding="utf-8")
    )
    raw = tomllib.loads(text)
    registry: Registry = {}
    for domain, slots in raw.items():
        for slot, providers in slots.items():
            name = f"{domain}.{slot}"
            registry[name] = Capability(
                name=name,
                primary=providers["primary"],
                challenger=providers.get("challenger"),
                fallback=providers.get("fallback"),
            )
    _validate(registry)
    return registry


def _validate(registry: Registry) -> None:
    """Enforce the architecture invariants on the loaded registry."""
    missing = _INTERNAL_CAPABILITIES - registry.keys()
    if missing:
        raise ValueError(f"capability registry misses internal capabilities: {sorted(missing)}")
    for name in _INTERNAL_CAPABILITIES:
        if registry[name].primary != "internal":
            raise ValueError(f"capability {name} must stay internal-owned (architecture §35)")
    for capability in registry.values():
        owners = [
            provider
            for provider in (capability.primary, capability.challenger, capability.fallback)
            if provider
        ]
        if len(owners) != len(set(owners)):
            raise ValueError(f"capability {capability.name} lists a provider twice")


def authority_rank(registry: Registry, capability: str, provider: str) -> int:
    """Authority rank of ``provider`` for ``capability`` (0 = primary).

    Providers not listed for the capability rank after every authority
    (higher is weaker; the exact value is len(authorities)).
    """
    authorities = registry[capability].authorities()
    try:
        return authorities.index(provider)
    except ValueError:
        return len(authorities)


def is_authority(registry: Registry, capability: str, provider: str) -> bool:
    """True when the provider is listed as an authority for the capability."""
    return provider in registry[capability].authorities()
