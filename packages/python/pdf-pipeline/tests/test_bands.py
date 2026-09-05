"""Phase 3.3/3.4 band + column detection tests on synthetic page items."""

from __future__ import annotations

from document_model.generated import schema_models as generated
from pdf_pipeline.page_structure import (
    BandStructure,
    cluster_graphics,
    detect_bands,
    items_from_objects,
)

PAGE_WIDTH = 600.0
PAGE_HEIGHT = 800.0


_COUNTER = iter(range(1, 10000))


def _uid() -> str:
    return f"00000000-0000-0000-0000-{next(_COUNTER):012d}"


def _span(
    x: float, y: float, width: float, height: float, text: str = "line"
) -> generated.TextSpan:
    return generated.TextSpan(
        objectType="textSpan",
        id=_uid(),
        pageId=_uid(),
        text=text,
        geometry=generated.Rect(kind="rect", x=x, y=y, width=width, height=height),
        font=generated.FontRef(name=""),
        fontSize=height,
    )


def _image(x: float, y: float, width: float, height: float) -> generated.ImageObject:
    return generated.ImageObject(
        objectType="imageObject",
        id=_uid(),
        pageId=_uid(),
        geometry=generated.Rect(kind="rect", x=x, y=y, width=width, height=height),
    )


def _lines(
    ranges: list[tuple[float, ...]], column: tuple[float, float]
) -> list[generated.TextSpan]:
    return [_span(column[0], y, column[1] - column[0], 10.0) for y, _ in ranges]


def test_single_column_title_and_body() -> None:
    items = items_from_objects(
        [
            _span(150, 50, 300, 14, "Title"),  # full width line
            *_lines([(y, 0) for y in range(100, 200, 14)], (70, 500)),
        ]
    )
    bands = detect_bands(page_id="page", page_width=PAGE_WIDTH, items=items)
    assert bands
    assert all(len(band.columns) == 1 for band in bands)
    assert all(band.layout_mode == "SINGLE_COLUMN" for band in bands)


def test_two_column_body_detected() -> None:
    left = [(float(y), 0.0) for y in range(100, 700, 14)]
    right = [(float(y), 0.0) for y in range(100, 700, 14)]
    items = items_from_objects([*_lines(left, (70, 280)), *_lines(right, (320, 530))])
    bands = detect_bands(page_id="page", page_width=PAGE_WIDTH, items=items)
    assert len(bands) >= 1
    assert any(band.layout_mode == "MULTI_COLUMN" and len(band.columns) == 2 for band in bands)


def test_title_then_columns_then_spanning_figure() -> None:
    title = [_span(100, 40, 400, 14, "Title")]
    body_left = _lines([(y, 0) for y in range(100, 300, 14)], (70, 280))
    body_right = _lines([(y, 0) for y in range(100, 300, 14)], (320, 530))
    figure = [_image(70, 360, 460, 80)]
    after_left = _lines([(y, 0) for y in range(500, 600, 14)], (70, 280))
    after_right = _lines([(y, 0) for y in range(500, 600, 14)], (320, 530))
    items = items_from_objects(
        [*title, *body_left, *body_right, *figure, *after_left, *after_right]
    )
    bands = detect_bands(page_id="page", page_width=PAGE_WIDTH, items=items)

    modes = [band.layout_mode for band in bands]
    assert "MULTI_COLUMN" in modes
    assert "SPANNING" in modes
    # The title band comes first; the spanning figure interrupts the flow.
    assert modes.index("SPANNING") > 0
    assert modes.index("SPANNING") < len(modes) - 1


def test_unbalanced_columns_keep_flow() -> None:
    # Left column ends early; right column continues further down.
    left = _lines([(y, 0) for y in range(100, 300, 14)], (70, 280))
    right = _lines([(y, 0) for y in range(100, 700, 14)], (320, 530))
    items = items_from_objects([*left, *right])
    bands = detect_bands(page_id="page", page_width=PAGE_WIDTH, items=items)
    multicolumn = [band for band in bands if band.layout_mode == "MULTI_COLUMN"]
    assert multicolumn
    # Left column items stay in one column, right items in the other.
    band = multicolumn[0]
    left_items = list(band.columns[0].items)
    right_items = list(band.columns[1].items)
    assert all(item.rect.x < 300 for item in left_items)
    assert all(item.rect.x >= 300 for item in right_items)


def test_equation_number_island_merges_back() -> None:
    # Equation body + a narrow "(1)" at the right margin must not form a
    # second column.
    items = items_from_objects(
        [
            _span(200, 100, 150, 12, "E = mc2"),
            _span(430, 100, 20, 12, "(1)"),
        ]
    )
    bands = detect_bands(page_id="page", page_width=PAGE_WIDTH, items=items)
    assert len(bands) == 1
    assert len(bands[0].columns) == 1


def test_graphic_cluster_precedes_column_detection() -> None:
    # Three boxes + connectors: the whole tikz diagram becomes one item so
    # its internal x-gaps cannot split columns.
    boxes = [
        generated.VectorObject(
            objectType="vectorObject",
            id=_uid(),
            pageId=_uid(),
            geometry=generated.Rect(kind="rect", x=x, y=100, width=60, height=30),
        )
        for x in (100, 200, 300)
    ]
    arrows = [
        generated.VectorObject(
            objectType="vectorObject",
            id=_uid(),
            pageId=_uid(),
            geometry=generated.Rect(kind="rect", x=160, y=112, width=40, height=4),
        ),
        generated.VectorObject(
            objectType="vectorObject",
            id=_uid(),
            pageId=_uid(),
            geometry=generated.Rect(kind="rect", x=260, y=112, width=40, height=4),
        ),
    ]
    items = cluster_graphics(items_from_objects([*boxes, *arrows]))
    graphics = [item for item in items if item.is_graphic]
    assert len(graphics) == 1
    assert len(graphics[0].group) == 5


def test_bands_are_y_ordered() -> None:
    items = items_from_objects(
        [
            _span(70, 500, 460, 10),
            _span(70, 100, 460, 10),
            _span(70, 300, 460, 10),
        ]
    )
    bands = detect_bands(page_id="page", page_width=PAGE_WIDTH, items=items)
    ys = [band.y_start for band in bands]
    assert ys == sorted(ys)


def test_band_ids_default_empty_until_assigned() -> None:
    band = BandStructure(band_id="", page_id="p", layout_mode="SINGLE_COLUMN", columns=[])
    assert band.band_id == ""
