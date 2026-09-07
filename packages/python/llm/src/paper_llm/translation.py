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
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from paper_llm.cache import TranslationCache
    from paper_llm.config import ProviderConfig

from document_model import stable_uuid
from document_model.generated import schema_models as generated

from paper_llm.config import load_translation_config
from paper_llm.context import build_translation_contexts
from paper_llm.terminology import (
    build_terminology,
    derive_dummy_terminology,
    load_manual_terminology,
)
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
        text, marks = translate_rich_text_body(request.text, request.marks, self._translate_text)
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


def translate_rich_text_body(
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


def placeholder_indices(text: str) -> set[int]:
    """Return placeholder indexes present in ``text``."""
    return {int(match.group(1)) for match in _PLACEHOLDER_PATTERN.finditer(text)}


def assert_placeholders_preserved(protected: str, translated: str) -> None:
    """Raise when the model dropped any placeholder tokens from ``protected``."""
    missing = placeholder_indices(protected) - placeholder_indices(translated)
    if missing:
        dropped = ", ".join(f"⟦{index}⟧" for index in sorted(missing))
        raise RuntimeError(f"translation dropped protected placeholders: {dropped}")


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


def create_provider(
    *,
    provider_model: str = "dummy",
    provider_config: ProviderConfig | None = None,
) -> TranslationProvider:
    """Build the configured translation provider.

    ``provider_config`` wins over environment variables so callers that already
    constructed a ``TranslationConfig`` do not get a second, possibly different,
    adapter from ``PAPER_LLM_*``.
    """
    if provider_model == "dummy":
        return DummyTranslationProvider()
    config = provider_config
    if config is None:
        config = load_translation_config().provider
    if config is None:
        raise RuntimeError("OpenAI-compatible provider requested but provider config is unset")
    from paper_llm.openai_compat import OpenAICompatProvider  # noqa: PLC0415

    return OpenAICompatProvider(config)


def translate_document(
    semantic: generated.SemanticDocument,
    provider: TranslationProvider | None = None,
    *,
    target_locale: str = "und-x-dummy",
    source_locale: str | None = None,
    terminology: list[generated.Term] | None = None,
    terminology_revision: str | None = None,
    provider_model: str = "dummy",
    terminology_file: Path | None = None,
    cache: TranslationCache | None = None,
    node_ids: set[str] | None = None,
) -> generated.TranslationLayer:
    """Build a TranslationLayer for ``semantic`` without mutating it."""
    provider = provider or DummyTranslationProvider()
    manual_terms = load_manual_terminology(terminology_file)
    if terminology is None:
        if provider_model == "dummy":
            terminology, auto_revision = derive_dummy_terminology(
                semantic, manual_terms=manual_terms
            )
        else:
            terminology, auto_revision = build_terminology(semantic, manual_terms=manual_terms)
    else:
        _, auto_revision = build_terminology(semantic, manual_terms=list(terminology))
    terminology_tuple = tuple(terminology)
    if terminology_revision is None:
        terminology_revision = auto_revision
    contexts = build_translation_contexts(
        semantic,
        target_locale=target_locale,
        source_locale=source_locale,
    )
    entries: list[generated.TranslationEntry] = []
    for node in semantic.nodes:
        if node_ids is not None and node.id not in node_ids:
            continue
        node_context = contexts.get(
            node.id,
            TranslationContext(target_locale=target_locale, source_locale=source_locale),
        )
        if node.kind == "TABLE" and isinstance(node.content, generated.TableContent):
            source_content = node.content
            result_content = _translate_table_content(
                source_content,
                provider,
                node_context,
                terminology=terminology_tuple,
                node_kind=node.kind,
                semantic_node_id=node.id,
                cache=cache,
                provider_model=provider_model,
                terminology_revision=terminology_revision,
                target_locale=target_locale,
            )
            entries.append(
                _make_entry(
                    node.id,
                    result_content,
                    source_content=source_content,
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
            result = _translate_node(
                source,
                provider,
                node_context,
                terminology=terminology_tuple,
                node_kind=node.kind,
                semantic_node_id=node.id,
                cache=cache,
                provider_model=provider_model,
                terminology_revision=terminology_revision,
                target_locale=target_locale,
            )
            content = source.model_copy(update={"text": result.text, "marks": result.marks})
            entries.append(
                _make_entry(
                    node.id,
                    content,
                    source_content=source,
                    confidence=result.confidence,
                    provider_model=provider_model,
                    terminology_revision=terminology_revision,
                    target_locale=target_locale,
                )
            )
    layer_kwargs: dict[str, Any] = {
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


def retranslate_nodes(
    semantic: generated.SemanticDocument,
    translation: generated.TranslationLayer,
    node_ids: set[str],
    provider: TranslationProvider | None = None,
    *,
    cache: TranslationCache | None = None,
) -> generated.TranslationLayer:
    """Re-translate selected nodes and merge into an existing TranslationLayer."""
    refreshed = translate_document(
        semantic,
        provider,
        target_locale=translation.targetLocale,
        source_locale=translation.sourceLocale,
        terminology=list(translation.terminology or []),
        terminology_revision=translation.terminologyRevision or "rev-0",
        provider_model=translation.providerModel or "dummy",
        cache=cache,
        node_ids=node_ids,
    )
    merged = {entry.semanticNodeId: entry for entry in translation.entries}
    for entry in refreshed.entries:
        merged[entry.semanticNodeId] = entry
    return translation.model_copy(update={"entries": list(merged.values())})


def _translate_node(
    source: generated.RichText,
    provider: TranslationProvider,
    context: TranslationContext,
    *,
    terminology: tuple[generated.Term, ...],
    node_kind: str,
    semantic_node_id: str,
    cache: TranslationCache | None,
    provider_model: str,
    terminology_revision: str,
    target_locale: str,
) -> TranslationResult:
    cache_key = _cache_key(
        semantic_node_id=semantic_node_id,
        content_digest=_content_digest(source),
        target_locale=target_locale,
        provider_model=provider_model,
        terminology_revision=terminology_revision,
    )
    if cache is not None and (cached := cache.get(cache_key)) is not None:
        return TranslationResult(text=cached.text, marks=cached.marks, confidence=cached.confidence)
    request = TranslationRequest(
        text=source.text,
        marks=list(source.marks),
        context=context,
        terminology=terminology,
        node_kind=node_kind,
        semantic_node_id=semantic_node_id,
    )
    result = provider.translate_request(request)
    if cache is not None:
        cache.put(cache_key, result)
    return result


def _translate_table_content(
    content: generated.TableContent,
    provider: TranslationProvider,
    context: TranslationContext,
    *,
    terminology: tuple[generated.Term, ...],
    node_kind: str,
    semantic_node_id: str,
    cache: TranslationCache | None,
    provider_model: str,
    terminology_revision: str,
    target_locale: str,
) -> generated.TableContent:
    """Translate every table cell while preserving grid shape (FR-TRANS-002)."""
    cells: list[generated.TableCell] = []
    for cell in content.cells:
        result = _translate_node(
            cell.content,
            provider,
            context,
            terminology=terminology,
            node_kind=node_kind,
            semantic_node_id=semantic_node_id,
            cache=cache,
            provider_model=provider_model,
            terminology_revision=terminology_revision,
            target_locale=target_locale,
        )
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


def _make_entry(
    semantic_node_id: str,
    content: generated.NodeContent,
    *,
    source_content: generated.NodeContent,
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
            content_digest=_content_digest(source_content),
            target_locale=target_locale,
            provider_model=provider_model,
            terminology_revision=terminology_revision,
        ),
        provenanceIds=[],
    )
