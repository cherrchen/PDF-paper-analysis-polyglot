"""Terminology discovery and manual override loading (M5 Phase 5.3)."""

# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false

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
    payload: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise TypeError("terminology file must contain a JSON array")
    terms: list[generated.Term] = []
    for item in payload:
        parsed = _term_from_mapping(item)
        if parsed is not None:
            terms.append(parsed)
    return terms


def _term_from_mapping(item: object) -> generated.Term | None:
    if not isinstance(item, dict):
        return None
    term = item.get("term")
    translation = item.get("preferredTranslation")
    if not isinstance(term, str) or not isinstance(translation, str):
        return None
    return generated.Term(
        term=term,
        preferredTranslation=translation,
        source="MANUAL",
        confidence=1.0,
        scope="DOCUMENT",
    )


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


def collect_terminology(
    semantic: generated.SemanticDocument,
    *,
    manual_terms: list[generated.Term] | None = None,
    provider_model: str,
) -> tuple[list[generated.Term], str, tuple[str, ...]]:
    """Return glossary terms, revision, and untranslated candidate phrases.

    Dummy providers still mint deterministic ``[TERM]`` preferred translations.
    Real providers receive discovered phrases as consistency hints until a
    preferred translation exists; they do not invent glossary entries.
    """
    if provider_model == "dummy":
        terms, revision = derive_dummy_terminology(semantic, manual_terms=manual_terms)
        return terms, revision, ()
    terms, revision = build_terminology(semantic, manual_terms=manual_terms)
    manual_keys = {term.term.lower() for term in terms}
    candidates = tuple(
        phrase for phrase in discover_candidate_terms(semantic) if phrase.lower() not in manual_keys
    )
    if candidates:
        digest = hashlib.sha256("\n".join(candidates).encode()).hexdigest()[:8]
        revision = f"{revision}:cand-{digest}"
    return terms, revision, candidates
