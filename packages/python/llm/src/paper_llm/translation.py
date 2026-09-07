"""M5 translation layer: structured provider protocol and TranslationLayer builder.

Rich-text contract: marks are never copied at source offsets after the text
changes. Providers receive a ``TranslationRequest`` with marks and context;
the engine protects marked spans with placeholders before delegating plain
text to the provider, then rebuilds marks at the new offsets. Lost
placeholders drop the marks rather than pointing at the wrong characters.
"""

from __future__ import annotations

import hashlib
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

from document_model import stable_uuid
from document_model.generated import schema_models as generated

from paper_llm.context import build_translation_contexts
from paper_llm.types import (
    TranslationContext,
    TranslationProvider,
    TranslationRequest,
    TranslationResult,
)

TRANSLATION_MARKER = "[TRANSLATED]"

# Node kinds whose RichText content is translated. BIBLIOGRAPHY_ENTRY is
# excluded (PRD FR-CITE-004): reference entries stay in the source
# language. RenderComposer falls back to SemanticDocument text.
TEXT_NODE_KINDS = frozenset({"HEADING", "PARAGRAPH", "FIGURE_CAPTION", "TABLE_CAPTION", "FOOTNOTE"})

# Marks whose spans must survive translation via placeholder protection.
_PROTECTED_MARK_TYPES = frozenset(
    {
        "CITATION",
        "FIGURE_REFERENCE",
        "TABLE_REFERENCE",
        "EQUATION_REFERENCE",
        "SECTION_REFERENCE",
        "INLINE_EQUATION",
        "FOOTNOTE_REFERENCE",
        "LINK",
    }
)

# Placeholders must survive a dummy prefix and not appear in papers.
_PLACEHOLDER = "⟦{index}⟧"
_PLACEHOLDER_PATTERN = re.compile(r"⟦(\d+)⟧")


class DummyTranslationProvider:
    """Prefixes text with the marker; no real translation happens."""

    def translate_request(self, request: TranslationRequest) -> TranslationResult:
        text, marks = _translate_rich_text_body(request.text, request.marks, self._translate_text)
        return TranslationResult(text=text, marks=marks, confidence=1.0)

    def _translate_text(self, text: str) -> str:
        return f"{TRANSLATION_MARKER} {text}"

    def translate(self, text: str) -> str:
        """Legacy convenience for tests that call the provider directly."""
        return self._translate_text(text)


def translate_rich_text(
    text: str,
    marks: list[generated.InlineMark],
    provider: TranslationProvider,
    *,
    context: TranslationContext | None = None,
) -> tuple[str, list[generated.InlineMark]]:
    """Translate ``text`` and rebuild marks at the translated offsets."""
    request = TranslationRequest(text=text, marks=marks, context=context or TranslationContext())
    result = provider.translate_request(request)
    return result.text, result.marks


def _translate_rich_text_body(
    text: str,
    marks: list[generated.InlineMark],
    translate_text: Callable[[str], str],
) -> tuple[str, list[generated.InlineMark]]:
    """Core rich-text engine: protect marks, translate, rebuild offsets."""
    if not marks:
        return translate_text(text), []
    protected_marks = [mark for mark in marks if mark.type in _PROTECTED_MARK_TYPES]
    if not protected_marks:
        translated = translate_text(text)
        prefix_shift = _prefix_shift(text, translated)
        if prefix_shift is not None:
            return translated, _shift_marks(marks, prefix_shift, len(translated))
        return _translate_with_placeholders(text, marks, translate_text)
    return _translate_with_placeholders(text, protected_marks, translate_text)


def _prefix_shift(source: str, translated: str) -> int | None:
    """Offset to add when ``translated`` is exactly a prefix plus ``source``."""
    if translated == source:
        return 0
    if translated.endswith(source) and len(translated) >= len(source):
        return len(translated) - len(source)
    return None


def _shift_marks(
    marks: list[generated.InlineMark], delta: int, text_len: int
) -> list[generated.InlineMark]:
    shifted: list[generated.InlineMark] = []
    for mark in marks:
        start = mark.start + delta
        end = mark.end + delta
        if 0 <= start < end <= text_len:
            shifted.append(mark.model_copy(update={"start": start, "end": end}))
    return shifted


def _translate_with_placeholders(
    text: str,
    marks: list[generated.InlineMark],
    translate_text: Callable[[str], str],
) -> tuple[str, list[generated.InlineMark]]:
    """Protect marked spans, translate, then restore marks at new offsets."""
    spans = _merged_mark_spans(marks)
    protected = text
    originals: list[str] = []
    for index, (start, end) in reversed(list(enumerate(spans))):
        originals.append(text[start:end])
        protected = protected[:start] + _PLACEHOLDER.format(index=index) + protected[end:]
    originals.reverse()
    translated_protected = translate_text(protected)
    rebuilt, new_marks = _restore_placeholders(translated_protected, originals, marks, spans)
    return rebuilt, new_marks


def _merged_mark_spans(marks: list[generated.InlineMark]) -> list[tuple[int, int]]:
    intervals = sorted({(mark.start, mark.end) for mark in marks if mark.end > mark.start})
    merged: list[tuple[int, int]] = []
    for start, end in intervals:
        if merged and start < merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _restore_placeholders(
    translated_protected: str,
    originals: list[str],
    marks: list[generated.InlineMark],
    spans: list[tuple[int, int]],
) -> tuple[str, list[generated.InlineMark]]:
    found: dict[int, tuple[int, int]] = {}
    rebuilt: list[str] = []
    cursor = 0
    for match in _PLACEHOLDER_PATTERN.finditer(translated_protected):
        index = int(match.group(1))
        if index >= len(originals):
            continue
        rebuilt.append(translated_protected[cursor : match.start()])
        start = sum(len(part) for part in rebuilt)
        rebuilt.append(originals[index])
        found[index] = (start, start + len(originals[index]))
        cursor = match.end()
    rebuilt.append(translated_protected[cursor:])
    text = "".join(rebuilt)
    remapped: list[generated.InlineMark] = []
    for mark in marks:
        span_index = _span_index_for_mark(mark, spans)
        if span_index is None or span_index not in found:
            continue
        new_start, new_end = found[span_index]
        span_start, _span_end = spans[span_index]
        remapped.append(
            mark.model_copy(
                update={
                    "start": new_start + (mark.start - span_start),
                    "end": new_start + (mark.end - span_start),
                }
            )
        )
        if remapped[-1].end > new_end:
            remapped.pop()
    return text, remapped


def _span_index_for_mark(mark: generated.InlineMark, spans: list[tuple[int, int]]) -> int | None:
    for index, (start, end) in enumerate(spans):
        if start <= mark.start and mark.end <= end:
            return index
    return None


def _cache_key(
    *,
    semantic_node_id: str,
    content_digest: str,
    target_locale: str,
    provider_model: str,
    terminology_revision: str,
) -> str:
    payload = (
        f"{semantic_node_id}:{content_digest}:{target_locale}:"
        f"{provider_model}:{terminology_revision}"
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _content_digest(content: generated.NodeContent) -> str:
    return hashlib.sha256(content.model_dump_json().encode()).hexdigest()[:16]


def _translate_table_content(
    content: generated.TableContent,
    provider: TranslationProvider,
    context: TranslationContext,
    *,
    node_kind: str,
    semantic_node_id: str,
) -> generated.TableContent:
    """Translate every table cell while preserving grid shape (FR-TRANS-002)."""
    cells: list[generated.TableCell] = []
    for cell in content.cells:
        request = TranslationRequest(
            text=cell.content.text,
            marks=list(cell.content.marks),
            context=context,
            node_kind=node_kind,
            semantic_node_id=semantic_node_id,
        )
        result = provider.translate_request(request)
        cells.append(
            cell.model_copy(
                update={
                    "content": cell.content.model_copy(
                        update={"text": result.text, "marks": result.marks}
                    )
                }
            )
        )
    return content.model_copy(update={"cells": cells})


def translate_document(
    semantic: generated.SemanticDocument,
    provider: TranslationProvider | None = None,
    *,
    target_locale: str = "und-x-dummy",
    source_locale: str | None = None,
    terminology: list[generated.Term] | None = None,
    terminology_revision: str = "rev-0",
    provider_model: str = "dummy",
) -> generated.TranslationLayer:
    """Build a TranslationLayer for ``semantic`` without mutating it."""
    provider = provider or DummyTranslationProvider()
    terminology_tuple = tuple(terminology or ())
    contexts = build_translation_contexts(
        semantic,
        target_locale=target_locale,
        source_locale=source_locale,
    )
    entries: list[generated.TranslationEntry] = []
    for node in semantic.nodes:
        node_context = contexts.get(
            node.id,
            TranslationContext(target_locale=target_locale, source_locale=source_locale),
        )
        if node.kind == "TABLE" and isinstance(node.content, generated.TableContent):
            translated = _translate_table_content(
                node.content,
                provider,
                node_context,
                node_kind=node.kind,
                semantic_node_id=node.id,
            )
            entries.append(
                _make_entry(
                    node.id,
                    translated,
                    provider_model=provider_model,
                    terminology_revision=terminology_revision,
                    target_locale=target_locale,
                )
            )
            continue
        text = getattr(node.content, "text", None)
        if node.kind in TEXT_NODE_KINDS and isinstance(text, str):
            source = node.content
            if not isinstance(source, generated.RichText):
                continue
            request = TranslationRequest(
                text=source.text,
                marks=list(source.marks),
                context=node_context,
                terminology=terminology_tuple,
                node_kind=node.kind,
                semantic_node_id=node.id,
            )
            result = provider.translate_request(request)
            content = source.model_copy(update={"text": result.text, "marks": result.marks})
            entries.append(
                _make_entry(
                    node.id,
                    content,
                    confidence=result.confidence,
                    provider_model=provider_model,
                    terminology_revision=terminology_revision,
                    target_locale=target_locale,
                )
            )
    layer_kwargs: dict[str, object] = {
        "schemaVersion": "0.2.0",
        "id": stable_uuid(semantic.id, "translation-layer", target_locale),
        "semanticDocumentId": semantic.id,
        "targetLocale": target_locale,
        "providerModel": provider_model,
        "terminologyRevision": terminology_revision,
        "entries": entries,
        "provenanceIds": [],
    }
    if source_locale is not None:
        layer_kwargs["sourceLocale"] = source_locale
    if terminology_tuple:
        layer_kwargs["terminology"] = list(terminology_tuple)
    return generated.TranslationLayer(**layer_kwargs)


def _make_entry(
    semantic_node_id: str,
    content: generated.NodeContent,
    *,
    confidence: float = 1.0,
    provider_model: str,
    terminology_revision: str,
    target_locale: str,
) -> generated.TranslationEntry:
    return generated.TranslationEntry(
        semanticNodeId=semantic_node_id,
        content=content,
        confidence=confidence,
        providerModel=provider_model,
        cacheKey=_cache_key(
            semantic_node_id=semantic_node_id,
            content_digest=_content_digest(content),
            target_locale=target_locale,
            provider_model=provider_model,
            terminology_revision=terminology_revision,
        ),
        provenanceIds=[],
    )
