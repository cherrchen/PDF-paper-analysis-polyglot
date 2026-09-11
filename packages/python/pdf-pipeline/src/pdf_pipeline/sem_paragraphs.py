"""Phase 4.1 paragraph recovery: CONTINUATION evidence + 1→N splitting.

Layout's reading flow carries CONTINUATION edges precisely where two text
regions continue the same block (column break, page break, figure
interruption). Semantic recovery consumes them here: a run of adjacent
flow regions joined by CONTINUATION edges becomes ONE node whose anchor
carries every source region (N Layout -> 1 Semantic).

The reverse case (Phase 4.1 deferred item, landed in M7) is
:func:`split_region_paragraphs`: one layout region whose text carries
SEVERAL paragraphs — blocking merged them — splits into one node per
paragraph, each anchored to the same region. Split signals are vertical
line gaps (paragraph skips) and embedded numbered headings; both are
deterministic. Region-level anchors mean the reader highlights the whole
block (character-level mapping stays deferred).

Callers pre-exclude non-content regions (headings, captions, front
matter, figures, tables) from the member set because layout labels are
noisy while the semantic role patterns are exact.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from itertools import pairwise
from typing import TYPE_CHECKING

from pdf_pipeline.sem_sections import heading_decision

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from document_model.generated import schema_models as generated

    from pdf_pipeline.fusion import RegionLine

# PDFium's soft-hyphen artifact inside extracted text.
_SOFT_HYPHEN = "\x02"
_WHITESPACE_RUN = re.compile(r"\s+")
_TRAILING_HYPHEN = re.compile(r"-{1,2}$")

# A vertical line gap beyond this multiple of the line height starts a new
# paragraph inside one region (blocking tolerates up to ~1 gap unit).
PARAGRAPH_GAP_FACTOR = 1.5


def clean_text(text: str) -> str:
    """Remove extraction artifacts and collapse whitespace runs.

    PDFium embeds raw ``\\r\\n`` and double spaces in span text; semantic
    text is normalized prose.
    """
    return _WHITESPACE_RUN.sub(" ", text.replace(_SOFT_HYPHEN, " ")).strip()


def join_region_text(first: str, second: str) -> str:
    """Join two region texts, resolving a line-final hyphenation.

    ``...meth-`` + ``od`` -> ``...method``; otherwise a single space joins.
    """
    left = first.rstrip()
    right = second.lstrip()
    if not left:
        return right
    if not right:
        return left
    if _TRAILING_HYPHEN.search(left) and right[:1].islower():
        return f"{_TRAILING_HYPHEN.sub('', left)}{right}"
    return f"{left} {right}"


def continuation_pairs(layout: generated.LayoutDocument) -> dict[tuple[str, str], float]:
    """CONTINUATION confidence keyed by (source, target) region pair."""
    return {
        (edge.source, edge.target): edge.confidence
        for edge in layout.readingFlow.edges
        if edge.reason == "CONTINUATION"
    }


def merged_region_text(
    group: Sequence[str],
    region_texts: Mapping[str, str],
) -> str:
    """Join one group's region texts in flow order."""
    text = ""
    for region_id in group:
        piece = clean_text(region_texts.get(region_id, "")).strip()
        if not piece:
            continue
        text = piece if not text else join_region_text(text, piece)
    return text


def group_continuation_confidence(
    group: Sequence[str],
    pairs: Mapping[tuple[str, str], float],
) -> float:
    """Minimum CONTINUATION confidence along one group."""
    scores = [
        confidence
        for first, second in pairwise(group)
        if (confidence := pairs.get((first, second))) is not None
    ]
    return min(scores) if scores else 0.5


@dataclass(frozen=True)
class ParagraphPiece:
    """One paragraph of a possibly split layout region (1 -> N baseline)."""

    region_id: str
    text: str
    is_heading: bool


def split_region_paragraphs(
    region_id: str,
    lines: Sequence[RegionLine],
) -> list[ParagraphPiece]:
    """Split one region's lines into paragraph pieces (1 Layout -> N Semantic).

    Boundaries: a line gap beyond ``PARAGRAPH_GAP_FACTOR *`` line height,
    or an embedded numbered heading line ("2 Methods") that does not open
    the region. A region that is already one paragraph returns a single
    piece. Heading pieces are single short heading lines; heading runs
    longer than one line stay paragraphs (conservative baseline).
    """
    if not lines:
        return []
    pieces: list[list[RegionLine]] = [[lines[0]]]
    for previous, line in pairwise(lines):
        previous_rect = previous.rect
        rect = line.rect
        gap = rect.y - (previous_rect.y + previous_rect.height)
        line_height = max(previous_rect.height, rect.height, 1.0)
        starts_heading = bool(_SPLIT_HEADING.match(line.text.strip()))
        # A single heading line already closed as its own piece ends the
        # heading: following prose is a separate paragraph.
        heading_ended = bool(
            _SPLIT_HEADING.match(pieces[-1][0].text.strip()) and len(pieces[-1]) == 1
        )
        if (
            (gap > PARAGRAPH_GAP_FACTOR * line_height and line.text.strip())
            or starts_heading
            or heading_ended
        ):
            pieces.append([line])
        else:
            pieces[-1].append(line)

    result: list[ParagraphPiece] = []
    for piece in pieces:
        text = _join_piece_lines(piece)
        if not text:
            continue
        is_heading = len(piece) == 1 and (
            heading_decision(text, None, numbered_only=True) is not None
        )
        result.append(ParagraphPiece(region_id=region_id, text=text, is_heading=is_heading))
    return result or [ParagraphPiece(region_id=region_id, text="", is_heading=False)]


# Heading lines that justify a split: numbered scholarly headings only.
_SPLIT_HEADING = re.compile(r"^\d+(?:\.\d+)*[.\s]\s*\S")


def _join_piece_lines(piece: Sequence[RegionLine]) -> str:
    text = ""
    for line in piece:
        cleaned = clean_text(line.text)
        if not cleaned:
            continue
        text = cleaned if not text else join_region_text(text, cleaned)
    return text
