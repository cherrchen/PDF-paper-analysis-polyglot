"""Phase 7.1 DocumentProbe tests on synthetic PhysicalDocuments.

The probe must derive document characteristics deterministically from
page objects alone: native/scanned ratios, math/table/image densities,
column estimate, and layout complexity (roadmap Phase 7.1).
"""

# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false
from __future__ import annotations

from pathlib import Path

import pypdfium2 as pdfium
import pytest
from document_model.generated import schema_models as generated
from pdf_pipeline.probe import probe_document

PAGE_WIDTH = 600.0
PAGE_HEIGHT = 800.0

_COUNTER = iter(range(20000, 30000))


def _uid() -> str:
    return f"00000000-0000-0000-0000-{next(_COUNTER):012d}"


def _span(
    x: float,
    y: float,
    width: float,
    height: float,
    text: str = "line of body text",
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


def _physical(
    pages: list[tuple[list[generated.TextSpan], list[generated.ImageObject]]],
) -> generated.PhysicalDocument:
    """Build a PhysicalDocument from (spans, images) per page."""
    result_pages: list[generated.PhysicalPage] = []
    objects: list[generated.PhysicalObject] = []
    for index, (spans, images) in enumerate(pages):
        page_id = _uid()
        for span in spans:
            span.pageId = page_id
        for image in images:
            image.pageId = page_id
        objects.extend([*spans, *images])
        result_pages.append(
            generated.PhysicalPage(
                id=page_id,
                index=index,
                geometry=generated.PageGeometry(
                    widthPt=PAGE_WIDTH,
                    heightPt=PAGE_HEIGHT,
                    rotation=0,
                    rawToCanonical=generated.Matrix(a=1, b=0, c=0, d=1, e=0, f=0),
                    canonicalToRaw=generated.Matrix(a=1, b=0, c=0, d=1, e=0, f=0),
                ),
                objectIds=[obj.id for obj in (*spans, *images)],
            )
        )
    return generated.PhysicalDocument(
        schemaVersion="0.1.0",
        id=_uid(),
        pages=result_pages,
        objects=objects,
        metadata=generated.PhysicalMetadata(),
    )


def _body_lines(column: tuple[float, float], y_start: int, y_end: int) -> list[generated.TextSpan]:
    return [
        _span(column[0], float(y), column[1] - column[0], 10.0) for y in range(y_start, y_end, 14)
    ]


def test_single_column_document_estimates_one_column() -> None:
    physical = _physical([(_body_lines((70, 530), 100, 600), [])])
    probe = probe_document(physical)
    assert probe.estimated_columns == 1
    assert probe.native_text_ratio == 1.0
    assert probe.scanned_page_ratio == 0.0
    assert probe.table_density == 0.0


def test_two_column_document_estimates_two_columns() -> None:
    physical = _physical(
        [(_body_lines((70, 280), 100, 700) + _body_lines((320, 530), 100, 700), [])]
    )
    probe = probe_document(physical)
    assert probe.estimated_columns == 2


def test_scanned_page_ratio_reflects_textless_pages() -> None:
    physical = _physical([(_body_lines((70, 530), 100, 600), []), ([], [])])
    probe = probe_document(physical)
    assert probe.native_text_ratio == 0.5
    assert probe.scanned_page_ratio == 0.5


def test_math_density_distinguishes_math_from_prose() -> None:
    prose = [_span(70, 100, 460, 10, "Plain prose (with one paren pair) about content")]
    math = [_span(70, 200, 200, 12, "E = mc^2 + α β γ")]  # noqa: RUF001
    probe = probe_document(_physical([(prose, [])]))
    prose_density = probe.math_density
    probe = probe_document(_physical([(math, [])]))
    assert probe.math_density > prose_density > 0.0
    assert probe.math_density >= 0.2


def test_table_density_counts_pages_with_aligned_numeric_rows() -> None:
    rows = [
        _span(70, float(y), 460, 10, f"row {i} 1.0 2.0 3.0")
        for i, y in enumerate(range(100, 160, 14))
    ]
    prose = _body_lines((70, 530), 300, 500)
    probe = probe_document(_physical([(prose, [])]))
    assert probe.table_density == 0.0
    probe = probe_document(_physical([(rows + prose, [])]))
    assert probe.table_density == 1.0


def test_image_density_averages_graphic_coverage() -> None:
    physical = _physical(
        [
            (_body_lines((70, 530), 100, 600), [_image(70, 650, 460, 100)]),
            (_body_lines((70, 530), 100, 600), []),
        ]
    )
    probe = probe_document(physical)
    expected = min(460.0 * 100.0 / (PAGE_WIDTH * PAGE_HEIGHT), 1.0)
    assert probe.image_density == expected / 2


def test_layout_complexity_grows_with_band_variety_and_graphics() -> None:
    single = probe_document(_physical([(_body_lines((70, 530), 100, 600), [])]))
    two_column_with_figure = probe_document(
        _physical(
            [
                (
                    _body_lines((70, 280), 100, 600) + _body_lines((320, 530), 100, 600),
                    [_image(70, 650, 460, 120)],
                )
            ]
        )
    )
    assert two_column_with_figure.layout_complexity > single.layout_complexity
    assert 0.0 <= single.layout_complexity <= 1.0


def test_empty_document_yields_zero_probe() -> None:
    probe = probe_document(_physical([([], [])]))
    assert probe.estimated_columns is None
    assert probe.native_text_ratio == 0.0
    assert probe.math_density == 0.0
    assert probe.layout_complexity == 0.0


def test_probe_is_deterministic() -> None:
    physical = _physical(
        [(_body_lines((70, 280), 100, 700) + _body_lines((320, 530), 100, 700), [])]
    )
    assert probe_document(physical) == probe_document(physical)


def test_pipeline_writes_probe_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """run_pipeline persists the probe artifact for routing diagnostics."""
    import json

    from pdf_pipeline import pipeline

    fixture = Path(__file__).resolve().parents[4] / "tests/fixtures/source/latex/build/smoke.pdf"
    if not fixture.exists():
        pytest.skip("smoke fixture PDF not built; run `just latex-smoke`")

    def _fake_compile(tex: Path, build_dir: Path) -> Path:
        del tex
        build_dir.mkdir(parents=True, exist_ok=True)
        out = build_dir / "target.pdf"
        doc = pdfium.PdfDocument.new()
        doc.new_page(612, 792)
        doc.save(out)
        doc.close()
        return out

    monkeypatch.setattr(pipeline, "compile_latex", _fake_compile)
    out = tmp_path / "ws"
    pipeline.run_pipeline(fixture, out)

    payload = json.loads((out / "probe.json").read_text())
    assert payload["probeVersion"]
    assert payload["native_text_ratio"] == 1.0
    assert payload["scanned_page_ratio"] == 0.0
    assert payload["estimated_columns"] in (1, 2)
