"""Phase 2.4 + M5 structured translation layer tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from paper_llm import TRANSLATION_MARKER, DummyTranslationProvider, translate_document
from paper_llm.translation import TEXT_NODE_KINDS, translate_rich_text

if TYPE_CHECKING:
    from document_model.generated import schema_models as generated

REPO_ROOT = Path(__file__).resolve().parents[4]
PIPELINE_TESTS = REPO_ROOT / "tests" / "fixtures" / "source" / "latex" / "build"
SEMANTIC_FIXTURE = (
    REPO_ROOT / "schemas" / "fixtures" / "semantic-document" / "paper-structure.valid.json"
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
        if node.kind in TEXT_NODE_KINDS and isinstance(getattr(node.content, "text", None), str)
    }
    table_ids = {node.id for node in semantic.nodes if node.kind == "TABLE"}
    assert {entry.semanticNodeId for entry in translation.entries} == expected_ids | table_ids
    for entry in translation.entries:
        node = original_by_id[entry.semanticNodeId]
        if node.kind == "TABLE":
            continue
        text = getattr(entry.content, "text", None)
        source_text = getattr(node.content, "text", None)
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


def test_translation_entries_carry_cache_keys() -> None:
    semantic = _smoke_semantic()
    translation = translate_document(semantic)
    assert translation.entries
    for entry in translation.entries:
        assert entry.cacheKey
        assert len(entry.cacheKey) == 16


def test_bibliography_entries_are_not_translated() -> None:
    pytest.importorskip("document_model")
    from document_model.generated import schema_models as generated

    semantic = generated.SemanticDocument.model_validate(
        json.loads(SEMANTIC_FIXTURE.read_text(encoding="utf-8"))
    )
    translation = translate_document(semantic)
    entry_ids = {node.id for node in semantic.nodes if node.kind == "BIBLIOGRAPHY_ENTRY"}
    translated_ids = {entry.semanticNodeId for entry in translation.entries}
    assert entry_ids
    assert "BIBLIOGRAPHY_ENTRY" not in TEXT_NODE_KINDS
    assert entry_ids.isdisjoint(translated_ids)
    by_id = {node.id: node for node in semantic.nodes}
    for entry in translation.entries:
        node = by_id[entry.semanticNodeId]
        assert node.kind != "BIBLIOGRAPHY_ENTRY"
        if node.kind == "TABLE":
            continue
        text = getattr(entry.content, "text", None)
        source_text = getattr(node.content, "text", None)
        assert isinstance(text, str)
        assert isinstance(source_text, str)
        assert text == f"{TRANSLATION_MARKER} {source_text}"


def test_table_cells_are_translated() -> None:
    pytest.importorskip("document_model")
    from document_model.generated import schema_models as generated

    semantic = generated.SemanticDocument.model_validate(
        json.loads(SEMANTIC_FIXTURE.read_text(encoding="utf-8"))
    )
    translation = translate_document(semantic)
    table_node = next(node for node in semantic.nodes if node.kind == "TABLE")
    entry = next(item for item in translation.entries if item.semanticNodeId == table_node.id)
    assert isinstance(entry.content, generated.TableContent)
    assert isinstance(table_node.content, generated.TableContent)
    assert len(entry.content.cells) == len(table_node.content.cells)
    for translated_cell, source_cell in zip(
        entry.content.cells, table_node.content.cells, strict=True
    ):
        assert translated_cell.content.text == f"{TRANSLATION_MARKER} {source_cell.content.text}"


def test_recovered_bibliography_entries_are_not_translated() -> None:
    pytest.importorskip("pdf_pipeline")
    from pdf_pipeline.layout import recover_layout_document
    from pdf_pipeline.physical import extract_physical_document
    from pdf_pipeline.pipeline import region_lines_from, region_texts_from
    from pdf_pipeline.semantic import recover_semantic_document

    pdf_path = PIPELINE_TESTS / "bibliography.pdf"
    if not pdf_path.exists():
        pytest.skip("bibliography fixture not built")
    physical = extract_physical_document(pdf_path.read_bytes())
    layout = recover_layout_document(physical)
    semantic = recover_semantic_document(
        layout,
        region_texts_from(physical, layout),
        lines=region_lines_from(physical, layout),
    )
    translation = translate_document(semantic)
    entry_ids = {node.id for node in semantic.nodes if node.kind == "BIBLIOGRAPHY_ENTRY"}
    assert entry_ids
    assert entry_ids.isdisjoint({entry.semanticNodeId for entry in translation.entries})


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
    from paper_llm.translation import TranslationRequest, TranslationResult

    class SurroundProvider:
        def translate_request(self, request: TranslationRequest) -> TranslationResult:
            from paper_llm.translation import _translate_rich_text_body

            text, marks = _translate_rich_text_body(
                request.text, request.marks, lambda value: f"<<{value}>>"
            )
            return TranslationResult(text=text, marks=marks)

    mark = generated.InlineMark(
        type="FOOTNOTE_REFERENCE", start=4, end=5, targetNodeId="fn-1", label="1"
    )
    translated, marks = translate_rich_text("see 1 now", [mark], SurroundProvider())
    assert translated.startswith("<<")
    assert len(marks) == 1
    assert translated[marks[0].start : marks[0].end] == "1"


def test_rewritten_text_without_placeholders_drops_stale_marks() -> None:
    from document_model.generated import schema_models as generated
    from paper_llm.translation import TranslationRequest, TranslationResult

    class ReplaceProvider:
        def translate_request(self, request: TranslationRequest) -> TranslationResult:
            from paper_llm.translation import _translate_rich_text_body

            text, marks = _translate_rich_text_body(
                request.text, request.marks, lambda _value: "fully rewritten without markers"
            )
            return TranslationResult(text=text, marks=marks)

    mark = generated.InlineMark(
        type="CITATION", start=4, end=7, targetNodeId="entry-1", label="[1]"
    )
    translated, marks = translate_rich_text("see [1] now", [mark], ReplaceProvider())
    assert translated == "fully rewritten without markers"
    assert marks == []
