"""Phase 4.1 paragraph recovery: CONTINUATION evidence -> merged blocks.

Layout's reading flow carries CONTINUATION edges precisely where two text
regions continue the same block (column break, page break, figure
interruption). Semantic recovery consumes them here: a run of adjacent
flow regions joined by CONTINUATION edges becomes ONE node whose anchor
carries every source region (N Layout -> 1 Semantic).

Callers pre-exclude non-content regions (headings, captions, front
matter, figures, tables) from the member set because layout labels are
noisy while the semantic role patterns are exact.
"""

from __future__ import annotations

import re
from itertools import pairwise
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from document_model.generated import schema_models as generated

# PDFium's soft-hyphen artifact inside extracted text.
_SOFT_HYPHEN = "\x02"
_WHITESPACE_RUN = re.compile(r"\s+")
_TRAILING_HYPHEN = re.compile(r"-{1,2}$")


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
