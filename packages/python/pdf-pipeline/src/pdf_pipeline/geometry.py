"""Rectangle geometry helpers shared by layout recovery stages.

All helpers operate on canonical page space rects (origin top-left, x
right, y down, unit PDF point). Non-rectangular geometry is narrowed to
its bounding rect at the normalization boundary (see pdf_pipeline.evidence).
"""

from __future__ import annotations

from document_model.generated import schema_models as generated


def as_rect(geometry: generated.Geometry) -> generated.Rect:
    """Bounding rect of any canonical geometry; rects pass through."""
    if isinstance(geometry, generated.Rect):
        return geometry
    # Geometry is a closed union; after the Rect branch only Quad/Polygon
    # remain and both expose ``points``.
    points: list[generated.Point] = geometry.points
    xs = [point.x for point in points]
    ys = [point.y for point in points]
    x, y = min(xs), min(ys)
    return generated.Rect(kind="rect", x=x, y=y, width=max(xs) - x, height=max(ys) - y)


def intersection_area(a: generated.Rect, b: generated.Rect) -> float:
    """Area of the axis-aligned intersection of two rects."""
    width = min(a.x + a.width, b.x + b.width) - max(a.x, b.x)
    height = min(a.y + a.height, b.y + b.height) - max(a.y, b.y)
    if width <= 0 or height <= 0:
        return 0.0
    return width * height


def union_rect(a: generated.Rect, b: generated.Rect) -> generated.Rect:
    """Smallest rect covering both inputs."""
    x = min(a.x, b.x)
    y = min(a.y, b.y)
    return generated.Rect(
        kind="rect",
        x=x,
        y=y,
        width=max(a.x + a.width, b.x + b.width) - x,
        height=max(a.y + a.height, b.y + b.height) - y,
    )


def iou(a: generated.Rect, b: generated.Rect) -> float:
    """Intersection-over-union of two rects."""
    union = a.width * a.height + b.width * b.height - intersection_area(a, b)
    if union <= 0:
        return 0.0
    return intersection_area(a, b) / union


def containment(a: generated.Rect, b: generated.Rect) -> float:
    """Fraction of ``b``'s area inside ``a``."""
    area = b.width * b.height
    if area <= 0:
        return 0.0
    return intersection_area(a, b) / area


def overlap_ratio(a: generated.Rect, b: generated.Rect) -> float:
    """Horizontal overlap divided by the narrower rect's width."""
    overlap = min(a.x + a.width, b.x + b.width) - max(a.x, b.x)
    narrower = min(a.width, b.width)
    if narrower <= 0:
        return 0.0
    return max(overlap, 0.0) / narrower


def reading_order_key(rect: generated.Rect, quantum_pt: float = 4.0) -> tuple[float, float]:
    """Stable within-column sort: top-to-bottom, then left-to-right.

    Y is quantized so two items on the same baseline (sub-point extraction
    jitter) stay left-to-right instead of inverting a two-column heading row.
    """
    return (round(rect.y / quantum_pt) * quantum_pt, rect.x)


def center(rect: generated.Rect) -> tuple[float, float]:
    """Center point of a rect."""
    return (rect.x + rect.width / 2, rect.y + rect.height / 2)


def vertical_gap(a: generated.Rect, b: generated.Rect) -> float:
    """Positive gap between vertically disjoint rects; 0 when they overlap."""
    if a.y + a.height <= b.y:
        return b.y - (a.y + a.height)
    if b.y + b.height <= a.y:
        return a.y - (b.y + b.height)
    return 0.0
