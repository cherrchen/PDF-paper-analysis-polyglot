"""Terminology discovery and manual override loading (M5 Phase 5.3)."""

# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from typing import TYPE_CHECKING

from document_model.generated import schema_models as generated

if TYPE_CHECKING:
    from pathlib import Path

_TERM_PATTERN = re.compile(r"\b[A-Z][a-z]+(?:[- ][A-Za-z][a-z]+)+\b")
_MIN_TERM_FREQUENCY = 2
_MAX_TERMS = 32


def load_manual_terminology(path: Path | None) -> list[generated.Term]:
    """Load user-provided glossary entries from a JSON file."""
    if path is None or not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise TypeError("terminology file must contain a JSON array")
    terms: list[generated.Term] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        term = item.get("term")
        translation = item.get("preferredTranslation")
        if not isinstance(term, str) or not isinstance(translation, str):
            continue
        terms.append(
            generated.Term(
                term=term,
                preferredTranslation=translation,
                source="MANUAL",
                confidence=1.0,
                scope="DOCUMENT",
            )
        )
    return terms


def discover_candidate_terms(semantic: generated.SemanticDocument) -> list[str]:
    """Extract repeated multi-word academic phrases from translatable text."""
    counts: Counter[str] = Counter()
    for node in semantic.nodes:
        text = getattr(node.content, "text", None)
        if not isinstance(text, str) or not text.strip():
            continue
        if node.kind in {"BIBLIOGRAPHY_ENTRY", "EQUATION"}:
            continue
        for match in _TERM_PATTERN.finditer(text):
            phrase = match.group(0).strip()
            if len(phrase) >= 8:
                counts[phrase] += 1
    return [
        phrase
        for phrase, frequency in counts.most_common(_MAX_TERMS)
        if frequency >= _MIN_TERM_FREQUENCY
    ]


def build_terminology(
    semantic: generated.SemanticDocument,
    *,
    manual_terms: list[generated.Term] | None = None,
    derived_terms: list[generated.Term] | None = None,
) -> tuple[list[generated.Term], str]:
    """Merge manual and derived glossary entries and return a revision id."""
    merged: dict[str, generated.Term] = {}
    for term in manual_terms or []:
        merged[term.term.lower()] = term
    for term in derived_terms or []:
        merged.setdefault(term.term.lower(), term)
    terms = list(merged.values())
    digest = hashlib.sha256(
        json.dumps([term.model_dump() for term in terms], sort_keys=True).encode()
    ).hexdigest()[:12]
    return terms, f"rev-{digest}"


def derive_dummy_terminology(
    semantic: generated.SemanticDocument,
    *,
    manual_terms: list[generated.Term] | None = None,
) -> tuple[list[generated.Term], str]:
    """Deterministic terminology for dummy/mock providers."""
    manual = manual_terms or []
    manual_keys = {term.term.lower() for term in manual}
    derived: list[generated.Term] = []
    for phrase in discover_candidate_terms(semantic):
        if phrase.lower() in manual_keys:
            continue
        derived.append(
            generated.Term(
                term=phrase,
                preferredTranslation=f"[TERM] {phrase}",
                source="DERIVED",
                confidence=0.8,
                scope="DOCUMENT",
            )
        )
    return build_terminology(semantic, manual_terms=manual, derived_terms=derived)
