"""Phase 4.6 footnote reference recovery.

Layout separates footnote bodies (FOOTNOTE regions, their own flow) and
defers reference evidence to semantic recovery (M3 handoff). Here, each
footnote body's leading marker (``1 ...`` / ``* ...``) names it; the
marker's twin in the body text — the same digit or symbol, possibly
with a PDFium-inserted space before a superscript — is the reference.
Both connect through a FOOTNOTE_OF relation plus a FOOTNOTE_REFERENCE
inline mark.

Matching is per footnote identity (page + label), not a document-global
label. Ordinary structural numbers such as ``Table 1`` do not win over a
real marker, and leftover footnotes are reported rather than silently
left unlinked.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from pdf_pipeline.footnotes import FOOTNOTE_MARKER

if TYPE_CHECKING:
    from collections.abc import Sequence

# A body marker rendered inline: digit(s) or a footnote symbol at a word
# end (superscripts merge into the span text), followed by punctuation,
# space, or end of line.
_BODY_REFERENCE = re.compile(r"(\d{1,2}|[*†‡§¶])(?=[\s.,;:!?)]|\Z)")

_MARKER_NUMBER = re.compile(r"^(\d{1,2})[\.\s]")
_MARKER_SYMBOL = re.compile(r"^([*†‡§¶])")

# Numbers that belong to figures/tables/sections are not footnote markers.
_STRUCTURAL_REF = re.compile(
    r"(?:Tables?|Tab\.|Figures?|Fig\.|Sections?|Sec\.|Equations?|Eq\.|"
    r"Chapters?|Pages?|Columns?|Rows?|Items?)\s*$",
    re.IGNORECASE,
)

# Letter-glue / PDFium space-before-superscript beat bare digits.
_MIN_LINK_SCORE = 0.6
_AMBIGUOUS_DELTA = 0.15


@dataclass(frozen=True)
class FootnoteBody:
    """One recovered footnote body, keyed by page and marker label."""

    node_id: str
    label: str
    page_id: str


@dataclass(frozen=True)
class ParagraphWindow:
    """A paragraph that may contain footnote markers."""

    node_id: str
    text: str
    page_ids: frozenset[str]


@dataclass(frozen=True)
class FootnoteAssignment:
    """One chosen body span for a footnote identity."""

    paragraph_id: str
    footnote_id: str
    start: int
    end: int
    label: str
    score: float
    ambiguous: bool


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
    Structural references such as ``Table 1`` are still returned; callers
    that need a unique link should use :func:`assign_footnote_references`.
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


def reference_candidate_score(text: str, start: int, end: int, label: str) -> float:
    """How likely ``text[start:end]`` is the in-text marker for ``label``."""
    if end <= start:
        return 0.0
    prefix = text[:start]
    if label.isdigit() and _STRUCTURAL_REF.search(prefix.rstrip()):
        return 0.0
    if start > 0 and text[start - 1].isalpha():
        return 0.95
    if (
        start > 0
        and text[start - 1].isspace()
        and prefix.rstrip()
        and prefix.rstrip()[-1].isalpha()
    ):
        return 0.7
    if start > 0 and text[start - 1] in ".,;:!?":
        return 0.4
    return 0.35


_Candidate = tuple[float, ParagraphWindow, int, int, str]


def assign_footnote_references(
    paragraphs: Sequence[ParagraphWindow],
    footnotes: Sequence[FootnoteBody],
) -> tuple[list[FootnoteAssignment], list[str]]:
    """Pick the best body span for each footnote identity.

    Identities are ``(page_id, label)``. Consumption is by footnote node
    id, so later pages may reuse ``1`` or ``*``. Ambiguous or unlinked
    footnotes produce messages; they never crash recovery.
    """
    by_identity: dict[tuple[str, str], list[FootnoteBody]] = {}
    for footnote in footnotes:
        by_identity.setdefault((footnote.page_id, footnote.label), []).append(footnote)
    scored = _score_footnote_candidates(paragraphs, footnotes)
    assignments: list[FootnoteAssignment] = []
    messages: list[str] = []
    claimed_spans: set[tuple[str, int, int]] = set()
    for identity, siblings in by_identity.items():
        if len(siblings) > 1:
            messages.append(f"duplicate footnote label {siblings[0].label} on page {identity[0]}")
        for footnote in siblings:
            assignment, message = _pick_footnote_assignment(
                footnote, scored.get(footnote.node_id, []), claimed_spans
            )
            if message:
                messages.append(message)
            if assignment is None:
                continue
            assignments.append(assignment)
            claimed_spans.add((assignment.paragraph_id, assignment.start, assignment.end))
    return assignments, messages


def _score_footnote_candidates(
    paragraphs: Sequence[ParagraphWindow],
    footnotes: Sequence[FootnoteBody],
) -> dict[str, list[_Candidate]]:
    scored: dict[str, list[_Candidate]] = {footnote.node_id: [] for footnote in footnotes}
    for paragraph in paragraphs:
        labels = {
            footnote.label
            for footnote in footnotes
            if footnote.page_id in paragraph.page_ids or not paragraph.page_ids
        }
        if not labels:
            continue
        for start, end, label in body_reference_spans(paragraph.text, labels):
            score = reference_candidate_score(paragraph.text, start, end, label)
            if score <= 0:
                continue
            for footnote in footnotes:
                if footnote.label != label:
                    continue
                if paragraph.page_ids and footnote.page_id not in paragraph.page_ids:
                    continue
                scored[footnote.node_id].append((score, paragraph, start, end, label))
    return scored


def _pick_footnote_assignment(
    footnote: FootnoteBody,
    scored: Sequence[_Candidate],
    claimed_spans: set[tuple[str, int, int]],
) -> tuple[FootnoteAssignment | None, str | None]:
    candidates = [
        item
        for item in scored
        if item[0] >= _MIN_LINK_SCORE and (item[1].node_id, item[2], item[3]) not in claimed_spans
    ]
    if not candidates:
        return None, f"unlinked footnote {footnote.label} ({footnote.node_id})"
    candidates.sort(key=lambda item: (-item[0], item[2]))
    best_score, paragraph, start, end, label = candidates[0]
    close = [item for item in candidates if best_score - item[0] <= _AMBIGUOUS_DELTA]
    distinct = {(item[1].node_id, item[2], item[3]) for item in close}
    ambiguous = len(distinct) > 1
    warning = f"ambiguous footnote reference {label} for {footnote.node_id}" if ambiguous else None
    return (
        FootnoteAssignment(
            paragraph_id=paragraph.node_id,
            footnote_id=footnote.node_id,
            start=start,
            end=end,
            label=label,
            score=best_score,
            ambiguous=ambiguous,
        ),
        warning,
    )
