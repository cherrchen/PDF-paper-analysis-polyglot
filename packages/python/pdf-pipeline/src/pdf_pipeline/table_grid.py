"""Shared deterministic table-grid analysis over text spans.

Used by both the layout-evidence baseline provider (region-level TABLE
guesses) and the simulated table-structure specialist (cell grids), so
detection and structuring agree on what a table is. All functions are
pure geometry over PhysicalDocument spans — no parser schemas.
"""

from __future__ import annotations

import itertools

from document_model.generated import schema_models as generated

from pdf_pipeline.geometry import as_rect

# A grid needs at least this many consecutive aligned multi-span rows.
TABLE_MIN_GRID_ROWS = 2
TABLE_MIN_GRID_COLUMNS = 2

# A run of aligned multi-span lines longer than this is multi-column body
# text (columns align line after line), not a table.
TABLE_MAX_GRID_ROWS = 12

# Adjacent grid columns must be separated by at least this fraction of the
# narrower column's width; multi-column gutters are proportionally tighter
# than table column gaps.
COLUMN_GAP_RATIO = 0.25

# Row/column clustering tolerances (PDF points).
CELL_ROW_GAP_FACTOR = 0.6
CELL_LINE_GAP_FACTOR = 0.4
CELL_COLUMN_TOLERANCE_PT = 8.0


def table_grid_regions(
    spans: list[generated.TextSpan],
) -> list[generated.Rect]:
    """Detect grid-like table regions from span geometry.

    A table is a maximal run of consecutive multi-span lines whose column
    count matches and whose column x-positions stay aligned within
    tolerance — a deterministic baseline for what Docling recovers from
    ruling lines in real PDFs. Multi-column body pages are rejected:
    their gutter is too tight relative to the column widths, and runs of
    aligned lines are longer than any table.
    """
    lines = cluster_lines(spans)
    grids: list[list[list[generated.TextSpan]]] = []
    current: list[list[generated.TextSpan]] = []
    current_centers: list[list[float]] = []

    def flush() -> None:
        if TABLE_MIN_GRID_ROWS <= len(current) <= TABLE_MAX_GRID_ROWS:
            flat = [span for line in current for span in line]
            if columns_separated(flat, len(current_centers[-1])):
                grids.append(current)

    for line in lines:
        if len(line) < TABLE_MIN_GRID_COLUMNS:
            flush()
            current = []
            current_centers = []
            continue
        centers = column_centers(line)
        if current and not columns_aligned(centers, current_centers[-1]):
            flush()
            current = []
            current_centers = []
        current.append(line)
        current_centers.append(centers)
    flush()
    return [grid_union_rect(lines_) for lines_ in grids]


def columns_aligned(a: list[float], b: list[float]) -> bool:
    return len(a) == len(b) and all(
        abs(x - y) <= CELL_COLUMN_TOLERANCE_PT for x, y in zip(a, b, strict=True)
    )


def columns_separated(spans: list[generated.TextSpan], column_count: int) -> bool:
    """Adjacent columns keep a proportional gap (rejects page gutters).

    Spans are assigned to their nearest column by left edge; for every
    adjacent column pair the horizontal gap between the column bounds
    must reach COLUMN_GAP_RATIO of the narrower column's width.
    """
    if column_count < 2:
        return True
    centers = _column_x_clusters(spans, column_count)
    columns: list[list[generated.TextSpan]] = [[] for _ in range(column_count)]
    for span in spans:
        rect = as_rect(span.geometry)
        columns[column_index(rect.x, centers)].append(span)
    bounds: list[tuple[float, float, float]] = []
    for cells in columns:
        if not cells:
            return False
        rects = [as_rect(span.geometry) for span in cells]
        left = min(rect.x for rect in rects)
        right = max(rect.x + rect.width for rect in rects)
        bounds.append((left, right, right - left))
    bounds.sort()
    for (_, right_a, width_a), (left_b, _, width_b) in itertools.pairwise(bounds):
        gap = left_b - right_a
        if gap < COLUMN_GAP_RATIO * max(min(width_a, width_b), 1.0):
            return False
    return True


def _column_x_clusters(spans: list[generated.TextSpan], column_count: int) -> list[float]:
    """Left-edge cluster seeds for ``column_count`` columns."""
    edges = sorted({round(as_rect(span.geometry).x, 1) for span in spans})
    centers: list[float] = []
    for x in edges:
        if centers and abs(x - centers[-1]) <= CELL_COLUMN_TOLERANCE_PT:
            continue
        centers.append(x)
    while len(centers) > column_count:
        # Merge the closest pair of adjacent seeds.
        pair = min(
            itertools.pairwise(centers),
            key=lambda pair: pair[1] - pair[0],
        )
        merged = (pair[0] + pair[1]) / 2
        centers = sorted([*(c for c in centers if c not in pair), merged])
    return centers


def ordered_spans(spans: list[generated.TextSpan]) -> list[generated.TextSpan]:
    """Page reading order (top-down, then left-right)."""
    return sorted(spans, key=lambda span: (as_rect(span.geometry).y, as_rect(span.geometry).x))


def cluster_lines(spans: list[generated.TextSpan]) -> list[list[generated.TextSpan]]:
    """Group spans into visual lines by shared y-band."""
    lines: list[list[generated.TextSpan]] = []
    for span in ordered_spans(spans):
        rect = as_rect(span.geometry)
        if lines:
            last_rect = as_rect(lines[-1][-1].geometry)
            line_gap = CELL_LINE_GAP_FACTOR * max(rect.height, last_rect.height)
            same_line = abs(rect.y - last_rect.y) <= line_gap or (
                rect.y < last_rect.y + last_rect.height and last_rect.y < rect.y + rect.height
            )
            if same_line:
                lines[-1].append(span)
                continue
        lines.append([span])
    return lines


def grid_union_rect(lines: list[list[generated.TextSpan]]) -> generated.Rect:
    rect = as_rect(lines[0][0].geometry)
    for line in lines:
        for span in line:
            other = as_rect(span.geometry)
            rect = generated.Rect(
                kind="rect",
                x=min(rect.x, other.x),
                y=min(rect.y, other.y),
                width=max(rect.x + rect.width, other.x + other.width) - min(rect.x, other.x),
                height=max(rect.y + rect.height, other.y + other.height) - min(rect.y, other.y),
            )
    return rect


def column_centers(spans: list[generated.TextSpan]) -> list[float]:
    """Cluster span left edges into column centers.

    Cell-level span extraction (physical layer) means each span is a
    cell; columns compare by left edge with a tolerance wide enough for
    right-aligned numeric columns whose left edges drift by half a glyph.
    """
    centers: list[float] = []
    for span in sorted(spans, key=lambda s: as_rect(s.geometry).x):
        x = as_rect(span.geometry).x
        if centers and abs(x - centers[-1]) <= CELL_COLUMN_TOLERANCE_PT:
            continue
        centers.append(x)
    return centers


def column_index(x: float, centers: list[float]) -> int:
    return min(range(len(centers)), key=lambda i: abs(x - centers[i]))


def cluster_rows(spans: list[generated.TextSpan]) -> list[list[generated.TextSpan]]:
    """Group table spans into rows by vertical position."""
    ordered = ordered_spans(spans)
    rows: list[list[generated.TextSpan]] = []
    for span in ordered:
        rect = as_rect(span.geometry)
        if rows:
            last = rows[-1][-1]
            last_rect = as_rect(last.geometry)
            gap = rect.y - (last_rect.y + last_rect.height)
            if gap <= CELL_ROW_GAP_FACTOR * max(rect.height, last_rect.height, 1.0):
                rows[-1].append(span)
                continue
        rows.append([span])
    return rows
