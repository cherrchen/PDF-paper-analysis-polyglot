"""Phase 4.7 bibliography structure and citation resolution.

A reference-section heading (``References``) opens a BIBLIOGRAPHY
container; entry-shaped paragraphs (``[n] ...``) become
BIBLIOGRAPHY_ENTRY nodes, and wrapped fragments join the previous entry
by flow adjacency after that heading. Numbered inline markers in body
paragraphs (``[1]``, ``[1,2]``, ``[1-3]``) resolve against those labels
into CITATION marks plus CITES relations; hyphen/en-dash ranges expand
inclusively. Unresolved numbers stay in the text and surface as issues.
"""

from __future__ import annotations

import re

_ENTRY_LABEL = re.compile(r"^\s*\[(\d{1,3})\]\s")

# Bracketed digit groups only; letters inside exclude math subscripts.
_CITATION_NUMBERS = re.compile(
    # separators: comma, semicolon, en dash, hyphen
    r"\[\s*(\d{1,3}(?:\s*[,;\u2013-]\s*\d{1,3})*)\s*\]"
)
_RANGE_SEPARATOR = re.compile(r"[\u2013-]")
_LIST_SEPARATOR = re.compile(r"[,;]")


def entry_label(text: str) -> str | None:
    """The ``[n]`` label leading a bibliography entry, if any."""
    match = _ENTRY_LABEL.match(text)
    return match.group(1) if match else None


def citation_spans(text: str) -> list[tuple[int, int, list[str]]]:
    """(start, end, numbers) for bracketed numeric citation markers.

    A marker must not hug a preceding word character, so math indices
    ``x[1]`` stay out while ``work [1] and`` resolves. Inclusive hyphen
    and en-dash ranges such as ``[1-3]`` expand to every integer in
    between.
    """
    spans: list[tuple[int, int, list[str]]] = []
    for match in _CITATION_NUMBERS.finditer(text):
        left = match.start() - 1
        if left >= 0 and text[left].isalnum():
            continue
        numbers = _expand_citation_numbers(match.group(1))
        if numbers:
            spans.append((match.start(), match.end(), numbers))
    return spans


def _expand_citation_numbers(inner: str) -> list[str]:
    """Split a citation body on commas/semicolons and expand hyphen ranges."""
    numbers: list[str] = []
    seen: set[str] = set()
    for part in _LIST_SEPARATOR.split(inner):
        token = part.strip()
        if not token:
            continue
        for number in _range_values(token):
            if number not in seen:
                seen.add(number)
                numbers.append(number)
    return numbers


def _range_values(token: str) -> list[str]:
    ends = [piece.strip() for piece in _RANGE_SEPARATOR.split(token) if piece.strip()]
    if len(ends) == 2 and ends[0].isdigit() and ends[1].isdigit():
        start, stop = int(ends[0]), int(ends[1])
        if start <= stop and stop - start <= 99:
            return [str(value) for value in range(start, stop + 1)]
        return [ends[0], ends[1]]
    return [token] if token.isdigit() else []
