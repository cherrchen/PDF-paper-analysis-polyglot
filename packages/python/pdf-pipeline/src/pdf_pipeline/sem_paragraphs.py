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

    region_ids: tuple[str, ...]
    text: str
    is_heading: bool

    @property
    def region_id(self) -> str:
        """First source region (stable id for node derivation)."""
        return self.region_ids[0]


def _is_numbered_heading_line(text: str) -> bool:
    """True when a line is a numbered scholarly heading, math-guarded."""
    return heading_decision(text.strip(), None, numbered_only=True) is not None


def split_region_paragraphs(
    region_id: str,
    lines: Sequence[RegionLine],
) -> list[ParagraphPiece]:
    """Split one region's lines into paragraph pieces (1 Layout -> N Semantic).

    Boundaries: a line gap beyond ``PARAGRAPH_GAP_FACTOR *`` line height,
    or an embedded numbered heading line ("2 Methods") that does not open
    the region. Heading detection reuses :func:`heading_decision` so math
    fragments such as ``2 dx = dy`` do not split a paragraph. A region
    that is already one paragraph returns a single piece. Heading pieces
    are single short heading lines; heading runs longer than one line
    stay paragraphs (conservative baseline).
    """
    if not lines:
        return []
    pieces: list[list[RegionLine]] = [[lines[0]]]
    for previous, line in pairwise(lines):
        previous_rect = previous.rect
        rect = line.rect
        gap = rect.y - (previous_rect.y + previous_rect.height)
        line_height = max(previous_rect.height, rect.height, 1.0)
        starts_heading = _is_numbered_heading_line(line.text)
        # A single heading line already closed as its own piece ends the
        # heading: following prose is a separate paragraph.
        heading_ended = len(pieces[-1]) == 1 and _is_numbered_heading_line(pieces[-1][0].text)
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
        is_heading = len(piece) == 1 and _is_numbered_heading_line(text)
        result.append(ParagraphPiece(region_ids=(region_id,), text=text, is_heading=is_heading))
    return result or [ParagraphPiece(region_ids=(region_id,), text="", is_heading=False)]


def paragraph_pieces_for_group(
    group: Sequence[str],
    lines_by_region: Mapping[str, Sequence[RegionLine]],
    texts: Mapping[str, str],
) -> list[ParagraphPiece] | None:
    """Split a continuation group, then rejoin pieces that still continue.

    Returns None when no region actually splits, so the caller keeps the
    classic N→1 merge. When any region yields more than one paragraph,
    boundary pieces that are not headings stay joined with
    :func:`join_region_text` and keep every source region on the piece.
    """
    any_split = False
    pieces: list[ParagraphPiece] = []
    for region_id in group:
        region_pieces = split_region_paragraphs(region_id, lines_by_region.get(region_id, []))
        if len(region_pieces) > 1:
            any_split = True
            incoming = list(region_pieces)
        else:
            incoming = [
                ParagraphPiece(
                    region_ids=(region_id,),
                    text=merged_region_text([region_id], texts),
                    is_heading=False,
                )
            ]
        if not pieces:
            pieces = incoming
            continue
        first, rest = incoming[0], incoming[1:]
        if not pieces[-1].is_heading and not first.is_heading and pieces[-1].text and first.text:
            seen = set(pieces[-1].region_ids)
            extra = tuple(rid for rid in first.region_ids if rid not in seen)
            pieces[-1] = ParagraphPiece(
                region_ids=(*pieces[-1].region_ids, *extra),
                text=join_region_text(pieces[-1].text, first.text),
                is_heading=False,
            )
            pieces.extend(rest)
        else:
            pieces.extend(incoming)
    if not any_split:
        return None
    return pieces


def _join_piece_lines(piece: Sequence[RegionLine]) -> str:
    text = ""
    for line in piece:
        cleaned = clean_text(line.text)
        if not cleaned:
            continue
        text = cleaned if not text else join_region_text(text, cleaned)
    return text
