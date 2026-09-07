"""Structured translation protocol types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from document_model.generated import schema_models as generated


@dataclass(frozen=True)
class TranslationContext:
    """Structured context passed to providers."""

    target_locale: str = ""
    source_locale: str | None = None
    document_title: str | None = None
    section_path: tuple[str, ...] = ()
    preceding_text: str | None = None
    following_text: str | None = None


@dataclass(frozen=True)
class TranslationRequest:
    """One translatable text segment with marks and context."""

    text: str
    marks: list[generated.InlineMark] = field(default_factory=list)
    context: TranslationContext = field(default_factory=TranslationContext)
    terminology: tuple[generated.Term, ...] = ()
    node_kind: str | None = None
    semantic_node_id: str | None = None


@dataclass(frozen=True)
class TranslationResult:
    """Provider output for one translated segment."""

    text: str
    marks: list[generated.InlineMark] = field(default_factory=list)
    confidence: float = 1.0


class TranslationProvider(Protocol):
    """Structured translation interface for M5 providers."""

    def translate_request(self, request: TranslationRequest) -> TranslationResult: ...
