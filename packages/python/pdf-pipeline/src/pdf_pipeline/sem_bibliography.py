"""Phase 4.7 bibliography structure and citation resolution.

A reference-section heading (``References``) opens a BIBLIOGRAPHY
container; entry-shaped paragraphs (``[n] ...``) become
BIBLIOGRAPHY_ENTRY nodes, and wrapped fragments join the previous entry.
Numbered inline markers in body paragraphs (``[1]``, ``[1,2]``,
``[1-3]``) resolve against those labels into CITATION marks plus CITES
relations; unresolved numbers stay in the text and surface as issues.
"""

from __future__ import annotations

import re

_ENTRY_LABEL = re.compile(r"^\s*\[(\d{1,3})\]\s")

# Bracketed digit groups only; letters inside exclude math subscripts.
_CITATION_NUMBERS = re.compile(
    # separators: comma, semicolon, en dash, hyphen
    r"\[\s*(\d{1,3}(?:\s*[,;\u2013-]\s*\d{1,3})*)\s*\]"
)
_SEPARATORS = re.compile(r"[,;\u2013-]")


def entry_label(text: str) -> str | None:
    """The ``[n]`` label leading a bibliography entry, if any."""
    match = _ENTRY_LABEL.match(text)
    return match.group(1) if match else None


def citation_spans(text: str) -> list[tuple[int, int, list[str]]]:
    """(start, end, numbers) for bracketed numeric citation markers.

    A marker must not hug a preceding word character, so math indices
    ``x[1]`` stay out while ``work [1] and`` resolves.
    """
    spans: list[tuple[int, int, list[str]]] = []
    for match in _CITATION_NUMBERS.finditer(text):
        left = match.start() - 1
        if left >= 0 and text[left].isalnum():
            continue
        numbers = [part.strip() for part in _SEPARATORS.split(match.group(1)) if part.strip()]
        if numbers:
            spans.append((match.start(), match.end(), numbers))
    return spans
