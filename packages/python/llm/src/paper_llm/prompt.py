"""Versioned translation prompts. Bump TRANSLATION_PROMPT_VERSION when text changes."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from paper_llm.types import TranslationRequest

TRANSLATION_PROMPT_VERSION = "2026-09-11.1"

SYSTEM_PROMPT = (
    "You are an academic paper translator. Preserve placeholder tokens of the "
    "form ⟦n:m⟧ exactly, including the numbers. Never duplicate, drop, add, or "
    "renumber placeholders. Never translate citation markers, equation "
    "references, or bibliography labels. Return only the translated text."
)


def build_translation_prompt(request: TranslationRequest, *, source_text: str | None = None) -> str:
    """Assemble the user prompt for one translation request."""
    sections: list[str] = []
    context = request.context
    if context.document_title:
        sections.append(f"Document title: {context.document_title}")
    if context.section_path:
        sections.append("Section path: " + " > ".join(context.section_path))
    if context.preceding_text:
        sections.append(f"Previous paragraph: {context.preceding_text}")
    if context.following_text:
        sections.append(f"Next paragraph: {context.following_text}")
    if request.terminology:
        glossary = "\n".join(
            f"- {term.term} => {term.preferredTranslation}" for term in request.terminology
        )
        sections.append(f"Terminology:\n{glossary}")
    if request.candidate_terms:
        candidates = "\n".join(f"- {term}" for term in request.candidate_terms)
        sections.append(
            f"Translate these terms consistently (no preferred translation yet):\n{candidates}"
        )
    sections.append(f"Target locale: {context.target_locale or 'unspecified'}")
    sections.append(f"Source text:\n{source_text if source_text is not None else request.text}")
    return "\n\n".join(sections)
