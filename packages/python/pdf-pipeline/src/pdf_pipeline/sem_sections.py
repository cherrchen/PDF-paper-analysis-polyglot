"""Phase 4.2 heading levels, front matter, and section classification.

Layout labels are noisy (section headings and dates both surface as
HEADING_LIKE or PARAGRAPH_LIKE depending on font size), so heading level
comes from the numbering pattern in the recovered text — the reliable
scholarly convention — and front matter comes from the page-1 prefix in
font size order. Both decisions are deterministic and observable.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from pdf_pipeline.fusion import RegionLine

# Numbered scholarly heading: "1", "1.2", "2.3.1" followed by text.
NUMBERED_HEADING = re.compile(r"^(\d+(?:\.\d+)*)[\.\s]")

# Reference-section aliases that end the body and start the bibliography.
BIBLIOGRAPHY_HEADINGS = re.compile(
    r"^(References|Bibliography|Works Cited)\s*:?\s*$", re.IGNORECASE
)

# Abstract lead-in inside front matter.
ABSTRACT_HEADING = re.compile(r"^Abstract\s*:?\s*$", re.IGNORECASE)

# ISO-ish date lines (\date in scholarly front matter).
DATE_LINE = re.compile(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}$")

# Author-ish short capitalized lines in front matter: at least two name tokens
# so a lone section title like ``Introduction`` is not an author.
AUTHOR_LINE = re.compile(r"^(?:[A-Z][A-Za-z.\-]+\s+|[A-Z]\.\s+){1,4}[A-Za-z][A-Za-z.\-]+[.,]?$")

# Unnumbered body headings that must end the title block even without Abstract.
BODY_SECTION_HEADINGS = re.compile(
    r"^(?:Introduction|Background|Related Works?|Methods?|Methodology|"
    r"Results?|Discussion|Conclusions?|Acknowledgemen?ts|"
    r"References|Bibliography|Appendix|Appendices|Future Work|"
    r"Limitations|Experiments?|Evaluation)\s*:?\s*$",
    re.IGNORECASE,
)

# Affiliation lines that stay in the title block.
AFFILIATION_LINE = re.compile(
    r"(University|Universität|Institute|Department|Dept\.|Laboratory|\bLab\b|"
    r"College|School of|Faculty|Center|Centre|Inc\.|Ltd\.|GmbH|ORCID)",
    re.IGNORECASE,
)

# A heading line is visually short; long capitalized strings are prose.
HEADING_MAX_CHARS = 80

_TERMINAL = ".!?:"
BODY_MIN_CHARS = 40


def heading_decision(
    text: str, label: str | None, *, numbered_only: bool = False
) -> tuple[int, str | None] | None:
    """(level, numbering) when the region text is a section heading.

    Numbered headings carry their level in the dot depth; unnumbered
    headings (``References``, or layout ``HEADING_LIKE`` lines like
    ``A displayed integral:``) are level 1. Math fragments (display
    equations mislabeled as headings) never become headings.
    """
    stripped = text.strip()
    if not stripped or len(stripped) > HEADING_MAX_CHARS:
        return None
    if re.search(r"[=^_\\]", stripped):
        return None  # math fragment, never a heading
    numbered = _numbered_heading(stripped)
    if numbered is not None:
        return numbered
    if numbered_only:
        return None
    unnumbered = BIBLIOGRAPHY_HEADINGS.match(stripped) or ABSTRACT_HEADING.match(stripped)
    if unnumbered or (label == "HEADING_LIKE" and _looks_like_heading_text(stripped)):
        return (1, None)
    return None


def _numbered_heading(stripped: str) -> tuple[int, str | None] | None:
    """(level, numbering) for ``2 Methods``-style headings; None otherwise."""
    numbered = NUMBERED_HEADING.match(stripped)
    if numbered is None:
        return None
    remainder = stripped[numbered.end() :].strip()
    if not remainder or not remainder[0].isalpha():
        return None  # "2021." is a year, "2 dx =" is math
    numbering = numbered.group(1)
    return (numbering.count(".") + 1, numbering)


def _looks_like_heading_text(stripped: str) -> bool:
    """Heading-shaped label-driven text: prose-like, never a math fragment.

    ``HEADING_LIKE`` is a font-size hint only; requiring English-shaped
    words (and rejecting operators) keeps a lone date from becoming a
    section heading while still admitting real titles.
    """
    if stripped.endswith((":", ";")):
        return False
    if "(" in stripped or ")" in stripped or re.search(r"[=+_\\^]", stripped):
        return False
    words = re.findall(r"[A-Za-z]{4,}", stripped)
    if not words:
        return False
    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 .,;:'\-]*", stripped))


def is_bibliography_heading(text: str) -> bool:
    """Whether a heading opens the bibliography section."""
    return bool(BIBLIOGRAPHY_HEADINGS.match(text.strip()))


def is_abstract_heading(text: str) -> bool:
    """Whether a line is a stand-alone ``Abstract`` lead-in."""
    return bool(ABSTRACT_HEADING.match(text.strip()))


def is_body_section_heading(text: str) -> bool:
    """Whether a line is an unnumbered body heading such as ``Introduction``."""
    return bool(BODY_SECTION_HEADINGS.match(text.strip()))


def _is_front_matter_line(text: str) -> bool:
    """Author, affiliation, or date — not a body section heading."""
    stripped = text.strip()
    if is_body_section_heading(stripped):
        return False
    if DATE_LINE.match(stripped) or AFFILIATION_LINE.search(stripped):
        return True
    return bool(AUTHOR_LINE.match(stripped) and len(stripped.split()) <= 6)


def classify_front_matter(
    flow_texts: Sequence[tuple[str, str]],
    labels: Mapping[str, str | None],
    lines: Mapping[str, Sequence[RegionLine]],
) -> dict[str, str]:
    """Region ids of the page-1 title block -> role (title/author/date/abstract).

    The block runs from the flow start to the first structural heading,
    abstract body, or body-sized sentence. Roles: the first
    ``HEADING_LIKE`` line is the title; a lone ``Abstract`` line names
    the abstract; ISO dates are dates; short capitalized lines are
    authors. Regions outside the returned mapping continue into the
    section tree.
    """
    boundary = _front_matter_boundary(flow_texts, labels)
    if not boundary:
        return {}
    (
        title_index,
        abstract_index,
        stop,
    ) = boundary
    title_font = _max_font(flow_texts[title_index][0], lines)
    roles: dict[str, str] = {}
    for index in range(stop):
        region_id, text = flow_texts[index]
        stripped = text.strip()
        if not stripped:
            continue
        roles[region_id] = _front_matter_role(
            index=index,
            title_index=title_index,
            abstract_index=abstract_index,
            stripped=stripped,
            title_font=title_font,
            region_id=region_id,
            lines=lines,
        )
    return roles


def _front_matter_boundary(
    flow_texts: Sequence[tuple[str, str]],
    labels: Mapping[str, str | None],
) -> tuple[int, int, int] | None:
    """(title index, abstract index, stop) for the page-1 title block.

    The block ends at the first numbered heading, at a real unnumbered
    body heading (``Introduction``), at the first body sentence after
    the title, or right after the abstract body. Author, affiliation,
    and date lines do not end it. ``None`` when no title line exists.
    """
    title_index = -1
    abstract_index = -1
    for index, (region_id, text) in enumerate(flow_texts):
        stripped = text.strip()
        if not stripped:
            continue
        label = labels.get(region_id)
        if title_index >= 0 and abstract_index < 0 and heading_decision(stripped, label):
            if is_abstract_heading(stripped):
                abstract_index = index
                continue
            if NUMBERED_HEADING.match(stripped) or not _is_front_matter_line(stripped):
                return (title_index, abstract_index, index)
            continue
        if title_index < 0 and label == "HEADING_LIKE":
            title_index = index
            continue
        if title_index >= 0 and _is_body_sentence(stripped):
            if abstract_index >= 0 and index == abstract_index + 1:
                return (title_index, abstract_index, index + 1)  # abstract body
            return (title_index, abstract_index, index)
    if title_index < 0:
        return None
    return (title_index, abstract_index, len(flow_texts))


def _front_matter_role(
    *,
    index: int,
    title_index: int,
    abstract_index: int,
    stripped: str,
    title_font: float,
    region_id: str,
    lines: Mapping[str, Sequence[RegionLine]],
) -> str:
    if index == title_index:
        return "title"
    if abstract_index >= 0 and index >= abstract_index:
        return "abstract-title" if index == abstract_index else "abstract"
    if DATE_LINE.match(stripped):
        return "date"
    font = _font_of(region_id, lines)
    small = bool(title_font and font < 0.85 * title_font)
    author_shaped = bool(AUTHOR_LINE.match(stripped) and len(stripped.split()) <= 6)
    return "author" if small or author_shaped else "front"


def _is_body_sentence(text: str) -> bool:
    return len(text) >= BODY_MIN_CHARS and text[-1] in _TERMINAL


def _max_font(region_id: str, lines: Mapping[str, Sequence[RegionLine]]) -> float:
    sizes = [line.font_size for line in lines.get(region_id, ())]
    return max(sizes) if sizes else 0.0


def _font_of(region_id: str, lines: Mapping[str, Sequence[RegionLine]]) -> float:
    sizes = [line.font_size for line in lines.get(region_id, ())]
    return max(sizes) if sizes else float("inf")
