"""Phase 2.4 dummy translation tests: identity preservation is the goal."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from paper_llm import TRANSLATION_MARKER, DummyTranslationProvider, translate_document

if TYPE_CHECKING:
    from document_model.generated import schema_models as generated

PIPELINE_TESTS = (
    Path(__file__).resolve().parents[4] / "tests" / "fixtures" / "source" / "latex" / "build"
)


def _smoke_semantic() -> generated.SemanticDocument:
    pytest.importorskip("pdf_pipeline")
    from pdf_pipeline.layout import recover_layout_document
    from pdf_pipeline.physical import extract_physical_document
    from pdf_pipeline.semantic import recover_semantic_document

    pdf_path = PIPELINE_TESTS / "smoke.pdf"
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
    return recover_semantic_document(layout, region_texts)


def test_dummy_prefixes_text() -> None:
    provider = DummyTranslationProvider()
    assert provider.translate("hello") == f"{TRANSLATION_MARKER} hello"


def test_translation_preserves_identity() -> None:
    semantic = _smoke_semantic()
    translated = translate_document(semantic)

    original_ids = [node.id for node in semantic.nodes]
    translated_ids = [node.id for node in translated.nodes]
    assert original_ids == translated_ids
    assert translated.rootId == semantic.rootId
    assert translated.relations == semantic.relations


def test_translation_rewrites_only_text_nodes() -> None:
    semantic = _smoke_semantic()
    translated = translate_document(semantic)

    original_by_id = {node.id: node for node in semantic.nodes}
    for node in translated.nodes:
        text = getattr(node.content, "text", None)
        source_text = getattr(original_by_id[node.id].content, "text", None)
        if node.kind in {"HEADING", "PARAGRAPH", "FIGURE_CAPTION"} and text and source_text:
            assert text.startswith(TRANSLATION_MARKER)
            # Source text is preserved after the marker.
            assert text.endswith(source_text)
        else:
            assert node.content == original_by_id[node.id].content


def test_translated_document_still_validates() -> None:
    pytest.importorskip("document_model")
    from document_model import dump_document, load_document

    semantic = _smoke_semantic()
    translated = translate_document(semantic)
    data = load_document("semantic-document", dump_document(translated))
    assert data.rootId == translated.rootId  # type: ignore[attr-defined]
