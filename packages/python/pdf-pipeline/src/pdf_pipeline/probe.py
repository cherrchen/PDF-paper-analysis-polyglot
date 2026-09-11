"""Phase 7.1 DocumentProbe: lightweight characteristics of a source document.

The probe answers "what kind of document is this?" from the
PhysicalDocument alone, before any evidence provider runs
(docs/architecture/document-architecture.md §41). Adaptive routing
(Phase 7.3) consumes the result to decide which providers to run — not
every parser runs on every document.

All signals are deterministic functions of the extracted page objects.
The probe result is an ad-hoc workspace artifact (``probe.json``), not a
canonical schema document: it is routing/report diagnostics in the same
category as the viewer manifest.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass

from document_model.generated import schema_models as generated

from pdf_pipeline.evidence.providers import FORMULA_CHARS, table_region_candidates
from pdf_pipeline.geometry import as_rect
from pdf_pipeline.page_structure import PageItem, detect_bands, items_from_objects
from pdf_pipeline.physical import MIN_CHARS_PER_PAGE
from pdf_pipeline.table_grid import table_grid_regions

PRODUCER = "pdf-pipeline.probe"
PRODUCER_VERSION = "0.1.0"

# Band layout modes tracked by complexity (FULL_WIDTH, SINGLE_COLUMN,
# MULTI_COLUMN, SPANNING); variety is normalized against the mode count
# minus one so a single-mode document scores 0.
MAX_BAND_MODES = 4

# Layout complexity weights: band-mode variety, graphic coverage, and
# pages whose column profile differs from the document mode.
COMPLEXITY_VARIETY_WEIGHT = 0.4
COMPLEXITY_GRAPHIC_WEIGHT = 0.3
COMPLEXITY_MIXED_WEIGHT = 0.3


@dataclass(frozen=True)
class ProbeResult:
    """Document-level characteristics used by adaptive routing.

    Ratios are in the closed interval [0, 1]. ``estimated_columns`` is the
    modal per-page column count across text-bearing pages (``None`` when
    the document has no meaningful text layer).
    """

    native_text_ratio: float
    scanned_page_ratio: float
    math_density: float
    table_density: float
    image_density: float
    estimated_columns: int | None
    layout_complexity: float

    def to_json(self) -> dict[str, float | int | None]:
        """Ad-hoc artifact form for ``probe.json``."""
        return asdict(self)


def probe_document(physical: generated.PhysicalDocument) -> ProbeResult:
    """Derive document characteristics from extracted page objects.

    Deterministic: the same PhysicalDocument always yields the same
    ProbeResult, so routing decisions are reproducible.
    """
    spans_by_page: dict[str, list[generated.TextSpan]] = {}
    graphics_by_page: dict[str, list[generated.ImageObject | generated.VectorObject]] = {}
    for obj in physical.objects:
        if isinstance(obj, generated.TextSpan):
            spans_by_page.setdefault(obj.pageId, []).append(obj)
        elif isinstance(obj, (generated.ImageObject, generated.VectorObject)):
            graphics_by_page.setdefault(obj.pageId, []).append(obj)

    page_count = len(physical.pages)
    native_pages = 0
    math_chars = 0
    text_chars = 0
    table_pages = 0
    graphic_ratio_sum = 0.0
    column_counts: Counter[int] = Counter()
    band_modes: set[str] = set()
    text_page_count = 0

    for page in physical.pages:
        spans = spans_by_page.get(page.id, [])
        graphics = graphics_by_page.get(page.id, [])
        page_area = max(page.geometry.widthPt * page.geometry.heightPt, 1.0)

        chars = sum(len(span.text.strip()) for span in spans)
        if chars >= MIN_CHARS_PER_PAGE:
            native_pages += 1
        math_chars += sum(1 for span in spans for char in span.text if char in FORMULA_CHARS)
        text_chars += chars

        if table_region_candidates(_ordered(spans)) or table_grid_regions(_ordered(spans)):
            table_pages += 1

        graphic_area = sum(
            as_rect(obj.geometry).width * as_rect(obj.geometry).height for obj in graphics
        )
        graphic_ratio_sum += min(graphic_area / page_area, 1.0)

        page_columns = _page_column_count(page, spans, graphics)
        if page_columns is not None:
            text_page_count += 1
            column_counts[page_columns] += 1
            band_modes.update(_page_band_modes(page, spans, graphics))

    native_text_ratio = native_pages / page_count if page_count else 0.0
    math_density = math_chars / text_chars if text_chars else 0.0
    table_density = table_pages / page_count if page_count else 0.0
    image_density = graphic_ratio_sum / page_count if page_count else 0.0

    estimated_columns: int | None = None
    mixed_ratio = 0.0
    if column_counts:
        modal_count, modal_pages = column_counts.most_common(1)[0]
        estimated_columns = modal_count
        if text_page_count:
            mixed_ratio = 1.0 - modal_pages / text_page_count
    variety = max(len(band_modes) - 1, 0) / (MAX_BAND_MODES - 1)
    complexity = min(
        1.0,
        COMPLEXITY_VARIETY_WEIGHT * variety
        + COMPLEXITY_GRAPHIC_WEIGHT * image_density
        + COMPLEXITY_MIXED_WEIGHT * mixed_ratio,
    )

    return ProbeResult(
        native_text_ratio=native_text_ratio,
        scanned_page_ratio=1.0 - native_text_ratio,
        math_density=math_density,
        table_density=table_density,
        image_density=image_density,
        estimated_columns=estimated_columns,
        layout_complexity=complexity,
    )


def _ordered(spans: list[generated.TextSpan]) -> list[generated.TextSpan]:
    return sorted(spans, key=lambda span: (as_rect(span.geometry).y, as_rect(span.geometry).x))


def _page_items(
    spans: list[generated.TextSpan],
    graphics: list[generated.ImageObject | generated.VectorObject],
) -> list[PageItem]:
    return items_from_objects([*spans, *graphics])


def _page_column_count(
    page: generated.PhysicalPage,
    spans: list[generated.TextSpan],
    graphics: list[generated.ImageObject | generated.VectorObject],
) -> int | None:
    """Modal column count across the page's bands, or None without text."""
    if not spans:
        return None
    bands = detect_bands(
        page_id=page.id,
        page_width=page.geometry.widthPt,
        items=_page_items(spans, graphics),
    )
    counts = [len(band.columns) for band in bands]
    if not counts:
        return None
    return Counter(counts).most_common(1)[0][0]


def _page_band_modes(
    page: generated.PhysicalPage,
    spans: list[generated.TextSpan],
    graphics: list[generated.ImageObject | generated.VectorObject],
) -> set[str]:
    if not spans:
        return set()
    bands = detect_bands(
        page_id=page.id,
        page_width=page.geometry.widthPt,
        items=_page_items(spans, graphics),
    )
    return {band.layout_mode for band in bands}
