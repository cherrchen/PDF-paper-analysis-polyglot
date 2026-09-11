"""Tests for translation cache."""

# pyright: reportUnknownMemberType=false, reportAttributeAccessIssue=false

from __future__ import annotations

from pathlib import Path

import pytest
from document_model.generated import schema_models as generated
from paper_llm.cache import TranslationCache
from paper_llm.translation import DummyTranslationProvider, translate_document
from paper_llm.types import TranslationRequest, TranslationResult


def _paragraph_semantic(text: str = "See the method.") -> generated.SemanticDocument:
    return generated.SemanticDocument.model_validate(
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
                    "content": {"text": text, "marks": []},
                    "attributes": {},
                    "confidence": {"score": 1.0},
                    "provenanceIds": [],
                },
            ],
            "relations": [],
            "provenanceIds": [],
        }
    )


def _term(preferred: str) -> generated.Term:
    return generated.Term(
        term="method",
        preferredTranslation=preferred,
        source="MANUAL",
        confidence=1.0,
        scope="DOCUMENT",
    )


@pytest.mark.unit
def test_cache_skips_provider_on_hit(tmp_path: Path) -> None:
    pytest.importorskip("pdf_pipeline")
    from pdf_pipeline.layout import recover_layout_document
    from pdf_pipeline.physical import extract_physical_document
    from pdf_pipeline.semantic import recover_semantic_document

    repo = Path(__file__).resolve().parents[4]
    pdf_path = repo / "tests/fixtures/source/latex/build/smoke.pdf"
    if not pdf_path.exists():
        pytest.skip("smoke fixture not built")
    physical = extract_physical_document(pdf_path.read_bytes())
    layout = recover_layout_document(physical)
    spans = {o.id: o for o in physical.objects if o.objectType == "textSpan"}
    region_texts = {
        region.id: " ".join(
            spans[obj_id].text for obj_id in region.physicalObjectIds if obj_id in spans
        )
        for region in layout.regions
        if region.kind == "TEXT"
    }
    semantic = recover_semantic_document(layout, region_texts)
    cache = TranslationCache(tmp_path / "cache.jsonl")
    first = translate_document(semantic, DummyTranslationProvider(), cache=cache)
    calls = 0

    class CountingProvider(DummyTranslationProvider):
        def translate_request(self, request: TranslationRequest) -> TranslationResult:
            nonlocal calls
            calls += 1
            return super().translate_request(request)

    second = translate_document(semantic, CountingProvider(), cache=cache)
    assert first.entries
    assert second.entries
    assert calls == 0


@pytest.mark.unit
def test_real_provider_terminology_revision_invalidates_cache(tmp_path: Path) -> None:
    semantic = _paragraph_semantic()
    cache = TranslationCache(tmp_path / "cache.jsonl")
    calls = 0

    class CountingProvider:
        def translate_request(self, request: TranslationRequest) -> TranslationResult:
            nonlocal calls
            calls += 1
            preferred = request.terminology[0].preferredTranslation if request.terminology else ""
            return TranslationResult(text=f"{preferred}:{request.text}", marks=[])

    first = translate_document(
        semantic,
        CountingProvider(),
        terminology=[_term("方法")],
        provider_model="openai-compat:mock",
        cache=cache,
        target_locale="zh-CN",
    )
    second = translate_document(
        semantic,
        CountingProvider(),
        terminology=[_term("方法")],
        provider_model="openai-compat:mock",
        cache=cache,
        target_locale="zh-CN",
    )
    third = translate_document(
        semantic,
        CountingProvider(),
        terminology=[_term("办法")],
        provider_model="openai-compat:mock",
        cache=cache,
        target_locale="zh-CN",
    )
    assert calls == 2
    assert first.terminologyRevision != third.terminologyRevision
    assert first.entries[0].content.text == second.entries[0].content.text
    assert "办法" in third.entries[0].content.text
    assert "方法" in first.entries[0].content.text


@pytest.mark.unit
def test_cache_misses_when_endpoint_or_context_changes(tmp_path: Path) -> None:
    semantic = _paragraph_semantic()
    cache = TranslationCache(tmp_path / "cache.jsonl")
    calls = 0

    class CountingProvider:
        def translate_request(self, request: TranslationRequest) -> TranslationResult:
            nonlocal calls
            calls += 1
            return TranslationResult(text=f"{calls}:{request.text}", marks=[])

    translate_document(
        semantic,
        CountingProvider(),
        provider_model="openai-compat:mock",
        provider_endpoint="http://a.example",
        cache=cache,
        target_locale="zh-CN",
    )
    translate_document(
        semantic,
        CountingProvider(),
        provider_model="openai-compat:mock",
        provider_endpoint="http://b.example",
        cache=cache,
        target_locale="zh-CN",
    )
    assert calls == 2

    extra_id = "00000000-0000-0000-0000-000000000104"
    extra = generated.SemanticNode.model_validate(
        {
            "id": extra_id,
            "kind": "PARAGRAPH",
            "parentId": "00000000-0000-0000-0000-000000000102",
            "children": [],
            "content": {"text": "Following context.", "marks": []},
            "attributes": {},
            "confidence": {"score": 1.0},
            "provenanceIds": [],
        }
    )
    root = semantic.nodes[0].model_copy(
        update={"children": [*semantic.nodes[0].children, extra_id]}
    )
    with_context = semantic.model_copy(update={"nodes": [root, semantic.nodes[1], extra]})
    before_context = calls
    translate_document(
        semantic,
        CountingProvider(),
        provider_model="openai-compat:mock",
        provider_endpoint="http://a.example",
        cache=cache,
        target_locale="zh-CN",
    )
    translate_document(
        with_context,
        CountingProvider(),
        provider_model="openai-compat:mock",
        provider_endpoint="http://a.example",
        cache=cache,
        target_locale="zh-CN",
    )
    assert calls > before_context + 1


@pytest.mark.unit
def test_failed_placeholder_translation_is_not_cached(tmp_path: Path) -> None:
    semantic = _paragraph_semantic("See [1].")
    mark = generated.InlineMark(
        type="CITATION", start=4, end=7, targetNodeId="entry-1", label="[1]"
    )
    paragraph = semantic.nodes[1]
    assert isinstance(paragraph.content, generated.RichText)
    semantic = semantic.model_copy(
        update={
            "nodes": [
                semantic.nodes[0],
                paragraph.model_copy(
                    update={"content": paragraph.content.model_copy(update={"marks": [mark]})}
                ),
            ]
        }
    )
    cache = TranslationCache(tmp_path / "cache.jsonl")
    calls = 0

    class BadThenGood:
        def translate_request(self, request: TranslationRequest) -> TranslationResult:
            nonlocal calls
            calls += 1
            from paper_llm.translation import translate_rich_text_body

            def complete(value: str) -> str:
                if calls == 1:
                    return value + " " + value
                return value

            text, marks = translate_rich_text_body(request.text, request.marks, complete)
            return TranslationResult(text=text, marks=marks)

    with pytest.raises(RuntimeError, match="altered protected placeholders"):
        translate_document(
            semantic,
            BadThenGood(),
            provider_model="openai-compat:mock",
            cache=cache,
            target_locale="zh-CN",
        )
    cache_file = tmp_path / "cache.jsonl"
    assert not cache_file.exists() or cache_file.read_text(encoding="utf-8").strip() == ""
    translate_document(
        semantic,
        BadThenGood(),
        provider_model="openai-compat:mock",
        cache=cache,
        target_locale="zh-CN",
    )
    assert calls == 2
