"""Phase 3.7 caption association: FigureRegion/TableRegion ↔ CaptionLikeRegion.

Association criteria (Roadmap M3 Phase 3.7): vertical distance, horizontal
alignment, font size, caption prefix, and region width. Conventions:
figure captions sit below their figure, table captions above their table.
Associations surface as LayoutGroups (FIGURE_BLOCK / TABLE_BLOCK) so the
semantic layer can recover CAPTION_OF relations without any geometry.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from pdf_pipeline.fusion import InternalRegion, dominant_label

# Caption prefixes; the kind prefix decides which region kind pairs.
_FIGURE_PREFIX = re.compile(r"^(Figure|Fig\.)\s*\d+", re.IGNORECASE)
_TABLE_PREFIX = re.compile(r"^Table\s*\d+", re.IGNORECASE)

# Association bounds.
CAPTION_MAX_DISTANCE_PT = 60.0
CAPTION_MIN_X_OVERLAP = 0.4
# Bonus threshold (caption about as wide as its main region) and hard
# rejection threshold (a caption can be wider than a centered figure, but
# never several times wider).
CAPTION_WIDTH_RATIO_MAX = 1.1
CAPTION_WIDTH_HARD_MAX = 2.5
CAPTION_FONT_FACTOR_MAX = 1.15

# Weighted score needs at least this to accept a pair.
CAPTION_MIN_SCORE = 0.6

# Score weights.
_W_DISTANCE = 0.35
_W_SIDE = 0.2
_W_OVERLAP = 0.25
_W_WIDTH = 0.1
_W_FONT = 0.1


@dataclass(frozen=True)
class CaptionAssociation:
    """One recovered main↔caption pair with its association score."""

    main_region_id: str
    caption_region_id: str
    group_kind: str  # FIGURE_BLOCK or TABLE_BLOCK
    score: float


def caption_kind(text: str) -> str | None:
    """'FIGURE' / 'TABLE' when the text carries a caption prefix."""
    if _FIGURE_PREFIX.match(text):
        return "FIGURE"
    if _TABLE_PREFIX.match(text):
        return "TABLE"
    return None


def _is_caption_candidate(region: InternalRegion) -> bool:
    if region.kind != "TEXT":
        return False
    if dominant_label(region) == "CAPTION_LIKE":
        return True
    return caption_kind(region.text.strip()) is not None


def _pairing_score(  # noqa: PLR0911 - each return is a distinct rejection reason
    caption: InternalRegion,
    main: InternalRegion,
    expected_prefix_kind: str | None,
) -> float | None:
    """Score one caption↔main pair; None when structurally impossible."""
    caption_rect = caption.rect
    main_rect = main.rect

    prefix_kind = caption_kind(caption.text.strip())
    if expected_prefix_kind == "FIGURE" and prefix_kind == "TABLE":
        return None
    if expected_prefix_kind == "TABLE" and prefix_kind == "FIGURE":
        return None

    if caption_rect.y >= main_rect.y + main_rect.height:
        distance = caption_rect.y - (main_rect.y + main_rect.height)
        preferred_side = main.kind == "FIGURE"
    elif main_rect.y >= caption_rect.y + caption_rect.height:
        distance = main_rect.y - (caption_rect.y + caption_rect.height)
        preferred_side = main.kind == "TABLE"
    else:
        return None
    if distance > CAPTION_MAX_DISTANCE_PT:
        return None

    overlap = min(caption_rect.x + caption_rect.width, main_rect.x + main_rect.width) - max(
        caption_rect.x, main_rect.x
    )
    narrower = min(caption_rect.width, main_rect.width)
    x_overlap_ratio = max(overlap, 0.0) / narrower if narrower > 0 else 0.0
    if x_overlap_ratio < CAPTION_MIN_X_OVERLAP:
        return None

    width_ratio = caption_rect.width / main_rect.width if main_rect.width > 0 else 0.0
    if width_ratio > CAPTION_WIDTH_HARD_MAX:
        return None

    font_ok = (
        main.font_size <= 0
        or caption.font_size <= 0
        or caption.font_size <= CAPTION_FONT_FACTOR_MAX * main.font_size
    )

    score = _W_DISTANCE * (1.0 - distance / CAPTION_MAX_DISTANCE_PT)
    score += _W_SIDE * (1.0 if preferred_side else 0.0)
    score += _W_OVERLAP * x_overlap_ratio
    if width_ratio <= CAPTION_WIDTH_RATIO_MAX:
        score += _W_WIDTH
    if font_ok:
        score += _W_FONT
    return score


def associate_captions(regions: list[InternalRegion]) -> list[CaptionAssociation]:
    """Greedy 1:1 caption association, best score first."""
    mains = [region for region in regions if region.kind in {"FIGURE", "TABLE"}]
    captions = [region for region in regions if _is_caption_candidate(region)]
    scored: list[tuple[float, InternalRegion, InternalRegion, str]] = []
    for caption in captions:
        prefix_kind = caption_kind(caption.text.strip())
        for main in mains:
            score = _pairing_score(caption, main, prefix_kind)
            if score is None or score < CAPTION_MIN_SCORE:
                continue
            group_kind = "FIGURE_BLOCK" if main.kind == "FIGURE" else "TABLE_BLOCK"
            scored.append((score, caption, main, group_kind))
    scored.sort(key=lambda item: (-item[0], item[1].region_id, item[2].region_id))

    used_captions: set[str] = set()
    used_mains: set[str] = set()
    associations: list[CaptionAssociation] = []
    for score, caption, main, group_kind in scored:
        if caption.region_id in used_captions or main.region_id in used_mains:
            continue
        used_captions.add(caption.region_id)
        used_mains.add(main.region_id)
        associations.append(
            CaptionAssociation(
                main_region_id=main.region_id,
                caption_region_id=caption.region_id,
                group_kind=group_kind,
                score=round(score, 4),
            )
        )
    return associations
