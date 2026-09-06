"""Phase 4.6 footnote reference recovery.

Layout separates footnote bodies (FOOTNOTE regions, their own flow) and
defers reference evidence to semantic recovery (M3 handoff). Here, each
footnote body's leading marker (``1 ...`` / ``* ...``) names it; the
marker's twin in the body text — a digit glued to a word end — is the
reference. Both connect through a FOOTNOTE_OF relation plus a
FOOTNOTE_REFERENCE inline mark.
"""

from __future__ import annotations

import re

from pdf_pipeline.footnotes import FOOTNOTE_MARKER

# A body marker rendered inline: digit(s) at a word end (superscripts merge
# into the span text), followed by punctuation, space, or end of line.
_BODY_REFERENCE = re.compile(r"(\d{1,2})(?=[\s.,;:!?)]|\Z)")

_MARKER_NUMBER = re.compile(r"^(\d{1,2})[\.\s]")


def footnote_marker_number(region_text: str) -> int | None:
    """The leading numeric marker of a footnote body, if any."""
    stripped = region_text.strip()
    if not FOOTNOTE_MARKER.match(stripped):
        return None
    marker = _MARKER_NUMBER.match(stripped)
    return int(marker.group(1)) if marker else None


def body_reference_spans(text: str, known_numbers: set[int]) -> list[tuple[int, int, int]]:
    """(start, end, number) for inline footnote markers in joined body text.

    Only digits matching a footnote marker on the page count, and the
    digit must hug a letter (``reference2 ``) so years (``in 2020``) and
    section refs (``see 3``) stay untouched.
    """
    spans: list[tuple[int, int, int]] = []
    for match in _BODY_REFERENCE.finditer(text):
        number = int(match.group(1))
        if number not in known_numbers:
            continue
        # Skip longer digit runs: "1990" is a year even if "0" could alias.
        left = match.start(1) - 1
        if left >= 0 and text[left].isdigit():
            continue
        spans.append((match.start(1), match.end(1), number))
    return spans
