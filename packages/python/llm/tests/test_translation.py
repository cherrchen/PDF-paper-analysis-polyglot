"""Phase 2.4 dummy TranslationLayer tests."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from paper_llm import TRANSLATION_MARKER, DummyTranslationProvider, translate_document
from paper_llm.translation import translate_rich_text

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
    before = semantic.model_dump()
    translation = translate_document(semantic)

    assert semantic.model_dump() == before
    assert translation.semanticDocumentId == semantic.id
    assert {entry.semanticNodeId for entry in translation.entries} <= {
        node.id for node in semantic.nodes
    }
    assert translation == translate_document(semantic)


def test_translation_rewrites_only_text_nodes() -> None:
    semantic = _smoke_semantic()
    translation = translate_document(semantic)

    original_by_id = {node.id: node for node in semantic.nodes}
    expected_ids = {
        node.id
        for node in semantic.nodes
        if node.kind in {"HEADING", "PARAGRAPH", "FIGURE_CAPTION", "TABLE_CAPTION"}
        and isinstance(getattr(node.content, "text", None), str)
    }
    assert {entry.semanticNodeId for entry in translation.entries} == expected_ids
    for entry in translation.entries:
        text = getattr(entry.content, "text", None)
        source_text = getattr(original_by_id[entry.semanticNodeId].content, "text", None)
        assert isinstance(text, str)
        assert isinstance(source_text, str)
        assert text == f"{TRANSLATION_MARKER} {source_text}"


def test_translation_layer_validates() -> None:
    pytest.importorskip("document_model")
    from document_model import dump_document, load_document

    semantic = _smoke_semantic()
    translation = translate_document(semantic)
    data = load_document("translation-layer", dump_document(translation))
    assert data == translation


def test_dummy_translation_shifts_mark_offsets() -> None:
    from document_model.generated import schema_models as generated

    mark = generated.InlineMark(
        type="CITATION", start=4, end=7, targetNodeId="entry-1", label="[1]"
    )
    translated, marks = translate_rich_text("see [1] now", [mark], DummyTranslationProvider())
    assert translated.startswith(f"{TRANSLATION_MARKER} ")
    assert len(marks) == 1
    assert translated[marks[0].start : marks[0].end] == "[1]"


def test_non_prefix_translation_rebuilds_marks_via_placeholders() -> None:
    from document_model.generated import schema_models as generated

    class SurroundProvider:
        def translate(self, text: str) -> str:
            return f"<<{text}>>"

    mark = generated.InlineMark(
        type="FOOTNOTE_REFERENCE", start=4, end=5, targetNodeId="fn-1", label="1"
    )
    translated, marks = translate_rich_text("see 1 now", [mark], SurroundProvider())
    assert translated.startswith("<<")
    assert len(marks) == 1
    assert translated[marks[0].start : marks[0].end] == "1"


def test_rewritten_text_without_placeholders_drops_stale_marks() -> None:
    from document_model.generated import schema_models as generated

    class ReplaceProvider:
        def translate(self, text: str) -> str:
            del text
            return "fully rewritten without markers"

    mark = generated.InlineMark(
        type="CITATION", start=4, end=7, targetNodeId="entry-1", label="[1]"
    )
    translated, marks = translate_rich_text("see [1] now", [mark], ReplaceProvider())
    assert translated == "fully rewritten without markers"
    assert marks == []
