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

# Author-year inline markers (Phase 4.7 author-year route): "(Vaswani et
# al., 2017)", "(Vaswani & Shazeer, 2017)", "(Smith 2020b)". The first
# surname plus the year forms the resolution key; the full bracketed
# span becomes the mark label.
_AUTHOR_YEAR_MARKER = re.compile(
    r"\((?P<surname>[A-Z][A-Za-z'\-]+)"
    r"(?:\s+(?:et al\.|and\s+[A-Z][A-Za-z'\-]+|&\s*[A-Z][A-Za-z'\-]+))?,?"
    r"\s+(?P<year>(?:19|20)\d{2}[a-z]?)\)"
)
# First capitalized token of an entry (after the [n] label) is its surname.
_ENTRY_SURNAME = re.compile(r"[A-Z][A-Za-z'\-]+")
_ENTRY_YEAR = re.compile(r"\b((?:19|20)\d{2}[a-z]?)\b")


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


def author_year_spans(text: str) -> list[tuple[int, int, str]]:
    """(start, end, key) for author-year citation markers.

    The key is ``surname:year`` (year keeps its disambiguation suffix, so
    ``2017a`` differs from ``2017``); entries resolve against
    :func:`entry_author_year_key`. A marker must not hug a preceding word
    character, mirroring the numeric bracket rule.
    """
    spans: list[tuple[int, int, str]] = []
    for match in _AUTHOR_YEAR_MARKER.finditer(text):
        left = match.start() - 1
        if left >= 0 and text[left].isalnum():
            continue
        key = f"{match.group('surname').lower()}:{match.group('year')}"
        spans.append((match.start(), match.end(), key))
    return spans


def entry_author_year_key(entry_text: str) -> str | None:
    """``surname:year`` resolution key for a bibliography entry text."""
    body = _ENTRY_LABEL.sub("", entry_text, count=1)
    surname = _ENTRY_SURNAME.search(body)
    year = _ENTRY_YEAR.search(body)
    if surname is None or year is None:
        return None
    return f"{surname.group(0).lower()}:{year.group(1)}"


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
