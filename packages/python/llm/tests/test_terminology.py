"""Tests for terminology discovery and overrides."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from paper_llm.terminology import (
    build_terminology,
    derive_dummy_terminology,
    load_manual_terminology,
)

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.unit
def test_load_manual_terminology(tmp_path: Path) -> None:
    path = tmp_path / "terms.json"
    path.write_text(
        json.dumps(
            [{"term": "semantic recovery", "preferredTranslation": "语义恢复"}],
        ),
        encoding="utf-8",
    )
    terms = load_manual_terminology(path)
    assert len(terms) == 1
    assert terms[0].source == "MANUAL"


@pytest.mark.unit
def test_build_terminology_revision_changes_with_content() -> None:
    from document_model.generated import schema_models as generated

    manual = [
        generated.Term(
            term="alpha",
            preferredTranslation="阿尔法",
            source="MANUAL",
            confidence=1.0,
            scope="DOCUMENT",
        )
    ]
    _, revision_a = build_terminology(
        generated.SemanticDocument.model_validate(
            {
                "schemaVersion": "0.1.0",
                "id": "00000000-0000-0000-0000-000000000101",
                "rootId": "00000000-0000-0000-0000-000000000102",
                "nodes": [
                    {
                        "id": "00000000-0000-0000-0000-000000000102",
                        "kind": "DOCUMENT",
                        "children": [],
                        "content": {"text": "", "marks": []},
                        "attributes": {},
                        "confidence": {"score": 1.0},
                        "provenanceIds": [],
                    }
                ],
                "relations": [],
                "provenanceIds": [],
            }
        ),
        manual_terms=manual,
    )
    manual.append(
        generated.Term(
            term="beta",
            preferredTranslation="贝塔",
            source="MANUAL",
            confidence=1.0,
            scope="DOCUMENT",
        )
    )
    _, revision_b = build_terminology(
        generated.SemanticDocument.model_validate(
            {
                "schemaVersion": "0.1.0",
                "id": "00000000-0000-0000-0000-000000000101",
                "rootId": "00000000-0000-0000-0000-000000000102",
                "nodes": [
                    {
                        "id": "00000000-0000-0000-0000-000000000102",
                        "kind": "DOCUMENT",
                        "children": [],
                        "content": {"text": "", "marks": []},
                        "attributes": {},
                        "confidence": {"score": 1.0},
                        "provenanceIds": [],
                    }
                ],
                "relations": [],
                "provenanceIds": [],
            }
        ),
        manual_terms=manual,
    )
    assert revision_a != revision_b


@pytest.mark.unit
def test_derive_dummy_terminology_is_deterministic() -> None:
    from document_model.generated import schema_models as generated

    semantic = generated.SemanticDocument.model_validate(
        {
            "schemaVersion": "0.1.0",
            "id": "00000000-0000-0000-0000-000000000101",
            "rootId": "00000000-0000-0000-0000-000000000102",
            "nodes": [
                {
                    "id": "00000000-0000-0000-0000-000000000102",
                    "kind": "DOCUMENT",
                    "children": ["00000000-0000-0000-0000-000000000103"],
                    "content": {"text": "", "marks": []},
                    "attributes": {},
                    "confidence": {"score": 1.0},
                    "provenanceIds": [],
                },
                {
                    "id": "00000000-0000-0000-0000-000000000103",
                    "kind": "PARAGRAPH",
                    "parentId": "00000000-0000-0000-0000-000000000102",
                    "children": [],
                    "content": {
                        "text": "Semantic Recovery Semantic Recovery semantic recovery",
                        "marks": [],
                    },
                    "attributes": {},
                    "confidence": {"score": 1.0},
                    "provenanceIds": [],
                },
            ],
            "relations": [],
            "provenanceIds": [],
        }
    )
    first, rev_a = derive_dummy_terminology(semantic)
    second, rev_b = derive_dummy_terminology(semantic)
    assert first == second
    assert rev_a == rev_b
