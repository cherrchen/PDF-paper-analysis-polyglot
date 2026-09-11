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
                        "text": "Semantic Recovery. Semantic Recovery.",
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


@pytest.mark.unit
def test_collect_terminology_exposes_candidates_for_real_providers() -> None:
    from document_model.generated import schema_models as generated
    from paper_llm.terminology import collect_terminology

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
                        "text": "Semantic Recovery. Semantic Recovery.",
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
    dummy_terms, _, dummy_candidates = collect_terminology(semantic, provider_model="dummy")
    real_terms, _, real_candidates = collect_terminology(
        semantic, provider_model="openai-compat:mock"
    )
    assert dummy_candidates == ()
    assert dummy_terms
    assert dummy_terms[0].preferredTranslation.startswith("[TERM]")
    assert real_terms == []
    assert "Semantic Recovery" in real_candidates


@pytest.mark.unit
def test_real_provider_prompt_includes_candidate_terms() -> None:
    from document_model.generated import schema_models as generated
    from paper_llm.translation import translate_document
    from paper_llm.types import TranslationRequest, TranslationResult

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
                        "text": "Semantic Recovery. Semantic Recovery.",
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
    seen: dict[str, tuple[str, ...]] = {}

    class CaptureProvider:
        def translate_request(self, request: TranslationRequest) -> TranslationResult:
            seen["candidates"] = request.candidate_terms
            return TranslationResult(text=request.text, marks=list(request.marks))

    translate_document(
        semantic,
        CaptureProvider(),
        provider_model="openai-compat:mock",
        target_locale="zh-CN",
    )
    assert "Semantic Recovery" in seen["candidates"]
