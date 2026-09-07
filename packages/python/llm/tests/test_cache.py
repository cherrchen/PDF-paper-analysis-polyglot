"""Tests for translation cache."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from paper_llm.cache import TranslationCache
from paper_llm.translation import DummyTranslationProvider, translate_document

if TYPE_CHECKING:
    from paper_llm.types import TranslationRequest, TranslationResult


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
