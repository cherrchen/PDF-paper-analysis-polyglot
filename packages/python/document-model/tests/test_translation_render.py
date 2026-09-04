"""Cross-layer validation for the M2 TranslationLayer and RenderDocument."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from document_model import validate_bundle_references

ROOT = Path(__file__).resolve().parents[4]


def _fixture(kind: str, name: str) -> dict[str, Any]:
    path = ROOT / "schemas" / "fixtures" / kind / name
    return json.loads(path.read_text(encoding="utf-8"))


def _bundle() -> dict[str, Any]:
    return {
        "physical": _fixture("physical-document", "two-page-two-column.valid.json"),
        "layout": _fixture("layout-document", "two-column-spanning-figure.valid.json"),
        "semantic": _fixture("semantic-document", "paper-structure.valid.json"),
        "translation": _fixture("translation-layer", "dummy-zh.valid.json"),
        "render": _fixture("render-document", "generic-academic.valid.json"),
        "mappings": _fixture("mapping", "three-binding-scenarios.valid.json"),
    }


def test_translation_and_render_references_resolve() -> None:
    assert validate_bundle_references(_bundle()) == []


def test_duplicate_and_unknown_translation_entries_are_rejected() -> None:
    bundle = _bundle()
    entry = deepcopy(bundle["translation"]["entries"][0])
    entry["semanticNodeId"] = "00000000-0000-0000-0000-000000000999"
    bundle["translation"]["entries"].extend([entry, deepcopy(entry)])

    issues = validate_bundle_references(bundle)
    assert any("duplicate" in issue for issue in issues)
    assert any("unknown semantic node" in issue for issue in issues)


def test_render_document_identity_must_match_mapping() -> None:
    bundle = _bundle()
    bundle["mappings"]["renderBindings"] = [
        {
            "id": "00000000-0000-0000-0000-000000000301",
            "renderDocumentId": "00000000-0000-0000-0000-000000000999",
            "renderAnchorIds": [],
        }
    ]

    issues = validate_bundle_references(bundle)
    assert any("renderDocumentId" in issue for issue in issues)
