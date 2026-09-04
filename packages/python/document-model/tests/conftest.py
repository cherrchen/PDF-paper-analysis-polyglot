"""Shared fixtures: canonical documents loaded from schemas/fixtures/."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

SCHEMA_ROOT = Path(__file__).resolve().parents[4] / "schemas"


def load_fixture(schema_dir: str, name: str) -> dict[str, Any]:
    path = SCHEMA_ROOT / "fixtures" / schema_dir / name
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def physical_data() -> dict[str, Any]:
    return load_fixture("physical-document", "two-page-two-column.valid.json")


@pytest.fixture(scope="session")
def layout_data() -> dict[str, Any]:
    return load_fixture("layout-document", "two-column-spanning-figure.valid.json")


@pytest.fixture(scope="session")
def semantic_data() -> dict[str, Any]:
    return load_fixture("semantic-document", "paper-structure.valid.json")


@pytest.fixture(scope="session")
def evidence_data() -> dict[str, Any]:
    return load_fixture("evidence", "mock-providers.valid.json")


@pytest.fixture(scope="session")
def mapping_data() -> dict[str, Any]:
    return load_fixture("mapping", "three-binding-scenarios.valid.json")
