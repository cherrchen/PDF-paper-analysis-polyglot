"""Tests for translation context construction."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from paper_llm.context import build_translation_contexts

REPO_ROOT = Path(__file__).resolve().parents[4]
SEMANTIC_FIXTURE = (
    REPO_ROOT / "schemas" / "fixtures" / "semantic-document" / "paper-structure.valid.json"
)


@pytest.mark.unit
def test_context_includes_section_path_and_neighbors() -> None:
    from document_model.generated import schema_models as generated

    semantic = generated.SemanticDocument.model_validate(
        json.loads(SEMANTIC_FIXTURE.read_text(encoding="utf-8"))
    )
    contexts = build_translation_contexts(semantic, target_locale="zh-CN")
    heading = next(node for node in semantic.nodes if node.id == "01J5M1FXTRHEAD00000000000Y")
    context = contexts[heading.id]
    assert context.target_locale == "zh-CN"
    assert context.document_title == "1. Introduction"
    assert "split into heading and paragraph" in context.section_path[-1]
    assert context.preceding_text is not None
    assert "Spanning paragraph" in context.preceding_text


@pytest.mark.unit
def test_table_context_receives_section_path() -> None:
    from document_model.generated import schema_models as generated

    semantic = generated.SemanticDocument.model_validate(
        json.loads(SEMANTIC_FIXTURE.read_text(encoding="utf-8"))
    )
    contexts = build_translation_contexts(semantic, target_locale="zh-CN")
    table = next(node for node in semantic.nodes if node.kind == "TABLE")
    context = contexts[table.id]
    assert context.section_path
