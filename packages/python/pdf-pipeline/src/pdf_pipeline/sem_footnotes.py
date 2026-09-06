"""Phase 4.6 footnote reference recovery.

Layout separates footnote bodies (FOOTNOTE regions, their own flow) and
defers reference evidence to semantic recovery (M3 handoff). Here, each
footnote body's leading marker (``1 ...`` / ``* ...``) names it; the
marker's twin in the body text — the same digit or symbol, possibly
with a PDFium-inserted space before a superscript — is the reference.
Both connect through a FOOTNOTE_OF relation plus a FOOTNOTE_REFERENCE
inline mark.
"""

from __future__ import annotations

import re

from pdf_pipeline.footnotes import FOOTNOTE_MARKER

# A body marker rendered inline: digit(s) or a footnote symbol at a word
# end (superscripts merge into the span text), followed by punctuation,
# space, or end of line.
_BODY_REFERENCE = re.compile(r"(\d{1,2}|[*†‡§¶])(?=[\s.,;:!?)]|\Z)")

_MARKER_NUMBER = re.compile(r"^(\d{1,2})[\.\s]")
_MARKER_SYMBOL = re.compile(r"^([*†‡§¶])")


def footnote_marker_label(region_text: str) -> str | None:
    """The leading marker of a footnote body (digit string or symbol)."""
    stripped = region_text.strip()
    if not FOOTNOTE_MARKER.match(stripped):
        return None
    numbered = _MARKER_NUMBER.match(stripped)
    if numbered:
        return numbered.group(1)
    symbol = _MARKER_SYMBOL.match(stripped)
    return symbol.group(1) if symbol else None


def footnote_marker_number(region_text: str) -> int | None:
    """The leading numeric marker of a footnote body, if any.

    Prefer :func:`footnote_marker_label` when symbol footnotes matter.
    """
    label = footnote_marker_label(region_text)
    return int(label) if label is not None and label.isdigit() else None


def body_reference_spans(text: str, known_labels: set[str]) -> list[tuple[int, int, str]]:
    """(start, end, label) for inline footnote markers in joined body text.

    PDFium often inserts a space before a superscript, so ``footnote 1``
    and ``efficiency1`` both count when ``1`` is a known marker on the
    page. Digit runs (``2020``) stay out. Unknown numbers never match.
    """
    spans: list[tuple[int, int, str]] = []
    for match in _BODY_REFERENCE.finditer(text):
        label = match.group(1)
        if label not in known_labels:
            continue
        left = match.start(1) - 1
        if label.isdigit() and left >= 0 and text[left].isdigit():
            continue
        spans.append((match.start(1), match.end(1), label))
    return spans
