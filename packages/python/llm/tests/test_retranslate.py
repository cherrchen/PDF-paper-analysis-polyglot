"""User-initiated retranslation: provider identity, cache bypass, mixed models."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from document_model.generated import schema_models as generated
from paper_llm.cache import TranslationCache
from paper_llm.translation import (
    DUMMY_PROVIDER_MODEL,
    retranslate_nodes,
    translate_document,
    translation_requires_provider,
)
from paper_llm.types import TranslationRequest, TranslationResult

if TYPE_CHECKING:
    from pathlib import Path

PARA_A = "00000000-0000-0000-0000-000000000103"
PARA_B = "00000000-0000-0000-0000-000000000104"


def _two_paragraphs() -> generated.SemanticDocument:
    return generated.SemanticDocument.model_validate(
        {
            "schemaVersion": "0.1.0",
            "id": "00000000-0000-0000-0000-000000000101",
            "rootId": "00000000-0000-0000-0000-000000000102",
            "nodes": [
                {
                    "id": "00000000-0000-0000-0000-000000000102",
                    "kind": "DOCUMENT",
                    "children": [PARA_A, PARA_B],
                    "content": {"text": "", "marks": []},
                    "attributes": {},
                    "confidence": {"score": 1.0},
                    "provenanceIds": [],
                },
                {
                    "id": PARA_A,
                    "kind": "PARAGRAPH",
                    "parentId": "00000000-0000-0000-0000-000000000102",
                    "children": [],
                    "content": {"text": "First paragraph.", "marks": []},
                    "attributes": {},
                    "confidence": {"score": 1.0},
                    "provenanceIds": [],
                },
                {
                    "id": PARA_B,
                    "kind": "PARAGRAPH",
                    "parentId": "00000000-0000-0000-0000-000000000102",
                    "children": [],
                    "content": {"text": "Second paragraph.", "marks": []},
                    "attributes": {},
                    "confidence": {"score": 1.0},
                    "provenanceIds": [],
                },
            ],
            "relations": [],
            "provenanceIds": [],
        }
    )


class VersionedProvider:
    def __init__(self, label: str) -> None:
        self.label = label
        self.calls = 0

    def translate_request(self, request: TranslationRequest) -> TranslationResult:
        self.calls += 1
        return TranslationResult(text=f"{self.label}-v{self.calls}:{request.text}", marks=[])


def _text(entry: generated.TranslationEntry) -> str:
    assert isinstance(entry.content, generated.RichText)
    return entry.content.text


def test_retranslate_records_actual_provider_and_isolates_cache(tmp_path: Path) -> None:
    semantic = _two_paragraphs()
    cache = TranslationCache(tmp_path / "cache.jsonl")
    first_provider = VersionedProvider("A")
    layer = translate_document(
        semantic,
        first_provider,
        provider_model="openai-compat:model-a",
        provider_endpoint="http://llm.example",
        cache=cache,
        target_locale="zh-CN",
    )
    assert layer.providerModel == "openai-compat:model-a"
    assert first_provider.calls == 2

    second_provider = VersionedProvider("B")
    updated = retranslate_nodes(
        semantic,
        layer,
        {PARA_A},
        second_provider,
        cache=cache,
        provider_model="openai-compat:model-b",
        provider_endpoint="http://llm.example",
        skip_cache_read=False,
    )
    by_id = {entry.semanticNodeId: entry for entry in updated.entries}
    assert by_id[PARA_A].providerModel == "openai-compat:model-b"
    assert by_id[PARA_B].providerModel == "openai-compat:model-a"
    assert _text(by_id[PARA_A]).startswith("B-v1:")
    assert _text(by_id[PARA_B]).startswith("A-v")
    assert updated.providerModel == "openai-compat:model-b"
    assert second_provider.calls == 1


def test_user_retranslate_skips_cache_read_for_selected_nodes(tmp_path: Path) -> None:
    semantic = _two_paragraphs()
    cache = TranslationCache(tmp_path / "cache.jsonl")
    provider = VersionedProvider("X")
    layer = translate_document(
        semantic,
        provider,
        provider_model="openai-compat:mock",
        cache=cache,
        target_locale="zh-CN",
    )
    assert provider.calls == 2
    original_b = next(entry for entry in layer.entries if entry.semanticNodeId == PARA_B)

    updated = retranslate_nodes(
        semantic,
        layer,
        {PARA_A},
        provider,
        cache=cache,
        provider_model="openai-compat:mock",
        skip_cache_read=True,
    )
    assert provider.calls == 3
    by_id = {entry.semanticNodeId: entry for entry in updated.entries}
    assert _text(by_id[PARA_A]).startswith("X-v3:")
    assert _text(by_id[PARA_B]) == _text(original_b)


def test_retranslate_requires_provider_model_for_non_dummy() -> None:
    semantic = _two_paragraphs()
    layer = translate_document(semantic, target_locale="zh-CN")
    with pytest.raises(ValueError, match="provider_model is required"):
        retranslate_nodes(semantic, layer, {PARA_A}, VersionedProvider("Z"))


def test_translation_requires_provider_detects_real_identity() -> None:
    semantic = _two_paragraphs()
    dummy = translate_document(semantic, target_locale="zh-CN")
    assert dummy.providerModel == DUMMY_PROVIDER_MODEL
    assert not translation_requires_provider(dummy)
    real = dummy.model_copy(update={"providerModel": "openai-compat:gpt"})
    assert translation_requires_provider(real)
