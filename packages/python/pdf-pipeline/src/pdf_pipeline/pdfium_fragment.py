# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportAttributeAccessIssue=false, reportCallIssue=false, reportPrivateUsage=false
"""PDFium page-fragment adapter. Isolates untyped PDFium access."""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c

if TYPE_CHECKING:
    from document_model.generated import schema_models as generated


def extract_pdf_fragment(
    pdf_bytes: bytes,
    *,
    page_index: int,
    rect: generated.Rect,
    canonical_to_raw: generated.Matrix,
) -> bytes:
    """Crop one page to ``rect`` (canonical space) and return a one-page PDF."""
    left, bottom, right, top = _raw_box(rect, canonical_to_raw)
    source = pdfium.PdfDocument(pdf_bytes)
    try:
        dest = pdfium.PdfDocument.new()
        dest.import_pages(source, pages=[page_index])
        page = dest[0]
        pdfium_c.FPDFPage_SetMediaBox(page, left, bottom, right, top)
        pdfium_c.FPDFPage_SetCropBox(page, left, bottom, right, top)
        buffer = io.BytesIO()
        dest.save(buffer)
        dest.close()
        return buffer.getvalue()
    finally:
        source.close()


def _raw_box(
    rect: generated.Rect, canonical_to_raw: generated.Matrix
) -> tuple[float, float, float, float]:
    corners = [
        _transform(canonical_to_raw, x, y)
        for x, y in (
            (rect.x, rect.y),
            (rect.x + rect.width, rect.y),
            (rect.x, rect.y + rect.height),
            (rect.x + rect.width, rect.y + rect.height),
        )
    ]
    xs = [point[0] for point in corners]
    ys = [point[1] for point in corners]
    return min(xs), min(ys), max(xs), max(ys)


def _transform(matrix: generated.Matrix, x: float, y: float) -> tuple[float, float]:
    return (
        matrix.a * x + matrix.c * y + matrix.e,
        matrix.b * x + matrix.d * y + matrix.f,
    )
