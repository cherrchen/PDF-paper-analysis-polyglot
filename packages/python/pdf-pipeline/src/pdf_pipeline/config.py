"""Operator configuration for evidence-provider selection (M8 batch E).

Mirrors ``paper_llm.config``: one frozen dataclass plus one environment
loader, so parser configuration has exactly one reader.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

REGISTRY_PATH_ENV = "PAPER_CAPABILITY_REGISTRY"


@dataclass(frozen=True)
class ParserConfig:
    """Overrides for which evidence provider owns which capability.

    ``registry_path`` names a TOML file with the same shape as the bundled
    ``data/capability-registry.toml``. ``None`` keeps the bundled registry
    (the deterministic sim ensemble), which stays the default until real
    tool output plus ``just benchmark`` justify changing a bundled primary.
    """

    registry_path: Path | None = None


def load_parser_config() -> ParserConfig:
    """Read parser configuration from the process environment."""
    raw = os.environ.get(REGISTRY_PATH_ENV)
    return ParserConfig(registry_path=Path(raw) if raw else None)
