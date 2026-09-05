"""Page furniture detection shared by providers and layout blocking.

Headers and footers are small-font short lines in the top/bottom page
strips. Splitting them out early keeps body text blocking clean and lets
the mock evidence provider speak about the same body content the internal
baseline sees.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pdf_pipeline.geometry import as_rect

if TYPE_CHECKING:
    from document_model.generated import schema_models as generated

# Page furniture strips (fraction of page height).
HEADER_STRIP = 0.06
FOOTER_STRIP = 0.85
FURNITURE_MAX_FONT_FACTOR = 0.9

# A footer page number is at most a few characters.
FOOTER_MAX_CHARS = 4


def font_size(span: generated.TextSpan) -> float:
    """Font size of a span; falls back to its rect height."""
    if span.fontSize is not None and span.fontSize > 0:
        return span.fontSize
    return as_rect(span.geometry).height


def body_font_size(spans: list[generated.TextSpan]) -> float:
    """Median font size of the given spans (body text estimate)."""
    sizes = sorted(font_size(span) for span in spans)
    if not sizes:
        return 0.0
    middle = len(sizes) // 2
    if len(sizes) % 2:
        return sizes[middle]
    return (sizes[middle - 1] + sizes[middle]) / 2


def split_furniture(
    spans: list[generated.TextSpan],
    page_height: float,
    body_font: float,
) -> tuple[list[generated.TextSpan], list[generated.TextSpan], list[generated.TextSpan]]:
    """Split page spans into (body, headers, footers).

    Conservative: only small-font short lines in the top/bottom strips are
    furniture; titles and abstract headers live in the same strips but are
    large, so they stay in the body.
    """
    body: list[generated.TextSpan] = []
    headers: list[generated.TextSpan] = []
    footers: list[generated.TextSpan] = []
    for span in spans:
        rect = as_rect(span.geometry)
        small = body_font <= 0 or font_size(span) <= FURNITURE_MAX_FONT_FACTOR * body_font
        short = len(span.text.strip()) <= 120
        if small and short and rect.y + rect.height <= HEADER_STRIP * page_height:
            headers.append(span)
        elif rect.y >= FOOTER_STRIP * page_height and (
            span.text.strip().isdigit() or (small and len(span.text.strip()) <= FOOTER_MAX_CHARS)
        ):
            footers.append(span)
        else:
            body.append(span)
    return body, headers, footers
