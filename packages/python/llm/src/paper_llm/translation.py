"""Phase 2.4 dummy translation layer.

Minimal TranslationLayer implementation: prefixes every translatable entry
with ``[TRANSLATED]`` while leaving SemanticDocument untouched.

Rich-text contract: marks are never copied at source offsets after the
text changes. A fixed prefix shifts offsets; any other rewrite protects
marked spans with placeholders and rebuilds them at the new locations.
Lost placeholders drop the marks rather than pointing at the wrong
characters.
"""

from __future__ import annotations

import re
from typing import Protocol

from document_model import stable_uuid
from document_model.generated import schema_models as generated

TRANSLATION_MARKER = "[TRANSLATED]"

# Node kinds whose text content is translated. BIBLIOGRAPHY_ENTRY is
# excluded (PRD FR-CITE-004): reference entries stay in the source
# language. RenderComposer falls back to SemanticDocument text.
TEXT_NODE_KINDS = frozenset({"HEADING", "PARAGRAPH", "FIGURE_CAPTION", "TABLE_CAPTION"})

# Placeholders must survive a dummy prefix and not appear in papers.
_PLACEHOLDER = "⟦{index}⟧"
_PLACEHOLDER_PATTERN = re.compile(r"⟦(\d+)⟧")


class TranslationProvider(Protocol):
    """Minimal translation interface for the Walking Skeleton."""

    def translate(self, text: str) -> str: ...


class DummyTranslationProvider:
    """Prefixes text with the marker; no real translation happens."""

    def translate(self, text: str) -> str:
        return f"{TRANSLATION_MARKER} {text}"


def translate_rich_text(
    text: str,
    marks: list[generated.InlineMark],
    provider: TranslationProvider,
) -> tuple[str, list[generated.InlineMark]]:
    """Translate ``text`` and rebuild marks at the translated offsets."""
    if not marks:
        return provider.translate(text), []
    translated = provider.translate(text)
    prefix_shift = _prefix_shift(text, translated)
    if prefix_shift is not None:
        return translated, _shift_marks(marks, prefix_shift, len(translated))
    return _translate_with_placeholders(text, marks, provider)


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
    provider: TranslationProvider,
) -> tuple[str, list[generated.InlineMark]]:
    """Protect marked spans, translate, then restore marks at new offsets."""
    spans = _merged_mark_spans(marks)
    protected = text
    originals: list[str] = []
    for index, (start, end) in reversed(list(enumerate(spans))):
        originals.append(text[start:end])
        protected = protected[:start] + _PLACEHOLDER.format(index=index) + protected[end:]
    originals.reverse()
    translated_protected = provider.translate(protected)
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


def translate_document(
    semantic: generated.SemanticDocument,
    provider: TranslationProvider | None = None,
) -> generated.TranslationLayer:
    """Build an independent dummy TranslationLayer for ``semantic``.

    SemanticDocument remains untouched. Entries reference stable node IDs and
    contain only locale-specific generated content.
    """
    provider = provider or DummyTranslationProvider()
    entries: list[generated.TranslationEntry] = []
    for node in semantic.nodes:
        text = getattr(node.content, "text", None)
        if node.kind in TEXT_NODE_KINDS and isinstance(text, str):
            source = node.content
            if not isinstance(source, generated.RichText):
                continue
            translated_text, marks = translate_rich_text(source.text, list(source.marks), provider)
            content = source.model_copy(update={"text": translated_text, "marks": marks})
            entries.append(
                generated.TranslationEntry(
                    semanticNodeId=node.id,
                    content=content,
                    confidence=1.0,
                    provenanceIds=[],
                )
            )
    target_locale = "und-x-dummy"
    return generated.TranslationLayer(
        schemaVersion="0.1.0",
        id=stable_uuid(semantic.id, "translation-layer", target_locale),
        semanticDocumentId=semantic.id,
        targetLocale=target_locale,
        entries=entries,
        provenanceIds=[],
    )
