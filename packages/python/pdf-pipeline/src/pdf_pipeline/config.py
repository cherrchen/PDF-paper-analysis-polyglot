"""Operator environment configuration (M8 batches E and F).

Mirrors ``paper_llm.config``: loaders read the process environment so
configuration has exactly one reader per concern.

``PAPER_PUBLISH_FAULT`` (see ``load_publish_fault``) is the batch-F operator
seam for exercising publish rollback from a real process.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

REGISTRY_PATH_ENV = "PAPER_CAPABILITY_REGISTRY"

PUBLISH_FAULT_ENV = "PAPER_PUBLISH_FAULT"


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


def load_publish_fault() -> str | None:
    """File name whose publish commit should fail, or ``None``.

    When ``PAPER_PUBLISH_FAULT`` names a published file (``manifest.json``,
    ``target.pdf``, ...), the publish transaction raises ``OSError`` instead
    of committing that file, so an operator or test process can exercise the
    rollback path end to end. Unset (or empty) means no behavior change.
    """
    raw = os.environ.get(PUBLISH_FAULT_ENV)
    return raw or None
