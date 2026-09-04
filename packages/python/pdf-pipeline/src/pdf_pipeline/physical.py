# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportAttributeAccessIssue=false
"""Phase 2.1 minimal PDF backend: PDFium bytes -> PhysicalDocument.

Only what the Walking Skeleton needs: pages, text spans, basic images,
page geometry, and rasterization of pages for later phases. Reading order,
semantics, captions, and citations are deliberately absent (physical layer
must stay objective).

Determinism: IDs are derived from the document fingerprint and stable
per-object counters, so parsing the same PDF bytes twice yields identical
PhysicalDocument bytes.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c
from document_model import dump_document, load_document
from document_model.generated import schema_models as generated

from pdf_pipeline.ids import stable_uuid

if TYPE_CHECKING:
    from pathlib import Path

PRODUCER = "pdf-pipeline.physical"
PRODUCER_VERSION = "0.1.0"


@dataclass(frozen=True)
class ExtractOptions:
    """Tunables for extraction. Defaults keep spans at rect granularity."""

    # Merge adjacent text rects whose vertical overlap and horizontal gap
    # stay within these bounds (PDF points). Keeps line fragments together.
    line_merge_gap_pt: float = 6.0
    line_merge_overlap_ratio: float = 0.5


def source_fingerprint(data: bytes) -> str:
    """Stable fingerprint of the source PDF bytes."""
    return hashlib.sha256(data).hexdigest()


def _deterministic_id(fingerprint: str, kind: str, *parts: object) -> str:
    """Opaque ID derived from source bytes + stable parts (see pdf_pipeline.ids)."""
    return stable_uuid(fingerprint, kind, *parts)


def _rotation_degrees(page: pdfium.PdfPage) -> generated.PageRotation:
    # pypdfium2 exposes degrees, not PDFium's raw 0..3 rotation constants.
    return cast("generated.PageRotation", page.get_rotation())


def _canonical_rect(
    left: float,
    bottom: float,
    right: float,
    top: float,
    transform: generated.Matrix,
) -> generated.Rect:
    corners = [
        _transform_point(transform, x, y)
        for x, y in ((left, bottom), (left, top), (right, bottom), (right, top))
    ]
    x_values = [point[0] for point in corners]
    y_values = [point[1] for point in corners]
    x = min(x_values)
    y = min(y_values)
    return generated.Rect(
        kind="rect",
        x=x,
        y=y,
        width=max(x_values) - x,
        height=max(y_values) - y,
    )


def _transform_point(matrix: generated.Matrix, x: float, y: float) -> tuple[float, float]:
    return (
        matrix.a * x + matrix.c * y + matrix.e,
        matrix.b * x + matrix.d * y + matrix.f,
    )


def _merge_line_fragments(
    fragments: list[tuple[float, float, float, float, str, float]],
    options: ExtractOptions,
) -> list[tuple[float, float, float, float, str, float]]:
    """Merge same-line text rects (l, b, r, t, text, font_size).

    Input order from PDFium is reading order within a line, so fragments are
    merged left-to-right when they vertically overlap and sit close.
    """
    merged: list[tuple[float, float, float, float, str, float]] = []
    for frag in fragments:
        if merged:
            prev = merged[-1]
            vertical_overlap = min(prev[3], frag[3]) - max(prev[1], frag[1])
            min_height = min(prev[3] - prev[1], frag[3] - frag[1])
            horizontal_gap = frag[0] - prev[2]
            if (
                min_height > 0
                and vertical_overlap / min_height >= options.line_merge_overlap_ratio
                and 0 <= horizontal_gap <= options.line_merge_gap_pt
            ):
                text_joiner = " " if horizontal_gap > 1.0 else ""
                merged[-1] = (
                    prev[0],
                    min(prev[1], frag[1]),
                    max(prev[2], frag[2]),
                    max(prev[3], frag[3]),
                    prev[4] + text_joiner + frag[4],
                    max(prev[5], frag[5]),
                )
                continue
        merged.append(frag)
    return merged


def _extract_text_spans(
    page: pdfium.PdfPage,
    *,
    page_id: str,
    raw_to_canonical: generated.Matrix,
    fingerprint: str,
    page_index: int,
    options: ExtractOptions,
) -> list[generated.TextSpan]:
    textpage = page.get_textpage()
    try:
        char_count = textpage.count_chars()
        if char_count == 0:
            return []
        rect_count = textpage.count_rects(0, char_count)
        fragments: list[tuple[float, float, float, float, str, float]] = []
        for rect_index in range(rect_count):
            left, bottom, right, top = textpage.get_rect(rect_index)
            text = textpage.get_text_bounded(left=left, bottom=bottom, right=right, top=top)
            if not text.strip():
                continue
            # Char height as a font-size estimate for the first char in rect.
            font_size = top - bottom
            fragments.append((left, bottom, right, top, text, font_size))
        spans: list[generated.TextSpan] = []
        for order, (left, bottom, right, top, text, font_size) in enumerate(
            _merge_line_fragments(fragments, options)
        ):
            span_id = _deterministic_id(fingerprint, "text", page_index, order)
            spans.append(
                generated.TextSpan(
                    objectType="textSpan",
                    id=span_id,
                    pageId=page_id,
                    text=text,
                    geometry=_canonical_rect(left, bottom, right, top, raw_to_canonical),
                    font=generated.FontRef(name=""),
                    fontSize=round(font_size, 2) or None,
                )
            )
        return spans
    finally:
        textpage.close()


def _extract_images(
    page: pdfium.PdfPage,
    *,
    page_id: str,
    raw_to_canonical: generated.Matrix,
    fingerprint: str,
    page_index: int,
) -> list[generated.ImageObject]:
    objects: list[generated.ImageObject] = []
    image_counter = 0
    # Deep walk reaches images nested inside Form XObjects.
    for obj in page.get_objects(max_depth=16):
        if obj.type != pdfium_c.FPDF_PAGEOBJ_IMAGE:
            continue
        left, bottom, right, top = obj.get_pos()
        if right - left <= 0 or top - bottom <= 0:
            continue
        objects.append(
            generated.ImageObject(
                objectType="imageObject",
                id=_deterministic_id(fingerprint, "image", page_index, image_counter),
                pageId=page_id,
                geometry=_canonical_rect(left, bottom, right, top, raw_to_canonical),
            )
        )
        image_counter += 1
    return objects


def _page_geometry(
    width: float, height: float, rotation: generated.PageRotation
) -> generated.PageGeometry:
    # get_size() reports displayed dimensions, while text/object bounds stay
    # in unrotated PDF user space. Build the exact raw↔canonical affine pair.
    raw_width, raw_height = (height, width) if rotation in {90, 270} else (width, height)
    if rotation == 0:
        forward = (1.0, 0.0, 0.0, -1.0, 0.0, raw_height)
        inverse = forward
    elif rotation == 90:
        forward = (0.0, 1.0, 1.0, 0.0, 0.0, 0.0)
        inverse = forward
    elif rotation == 180:
        forward = (-1.0, 0.0, 0.0, 1.0, raw_width, 0.0)
        inverse = forward
    else:
        forward = (0.0, -1.0, -1.0, 0.0, raw_height, raw_width)
        inverse = (0.0, -1.0, -1.0, 0.0, raw_width, raw_height)
    raw_to_canonical = generated.Matrix(
        a=forward[0], b=forward[1], c=forward[2], d=forward[3], e=forward[4], f=forward[5]
    )
    canonical_to_raw = generated.Matrix(
        a=inverse[0], b=inverse[1], c=inverse[2], d=inverse[3], e=inverse[4], f=inverse[5]
    )
    return generated.PageGeometry(
        widthPt=width,
        heightPt=height,
        rotation=rotation,
        rawToCanonical=raw_to_canonical,
        canonicalToRaw=canonical_to_raw,
    )


def extract_physical_document(
    source: bytes | Path,
    *,
    options: ExtractOptions | None = None,
) -> generated.PhysicalDocument:
    """Parse PDF bytes into a validated PhysicalDocument.

    Deterministic: identical input bytes yield identical output documents,
    including IDs (see :func:`_deterministic_id`).
    """
    options = options or ExtractOptions()
    data = source if isinstance(source, bytes) else source.read_bytes()
    fingerprint = source_fingerprint(data)
    document_id = _deterministic_id(fingerprint, "document")

    pdf = pdfium.PdfDocument(data)
    try:
        pages: list[generated.PhysicalPage] = []
        objects: list[generated.PhysicalObject] = []
        for page_index in range(len(pdf)):
            page = pdf[page_index]
            width, height = page.get_size()
            page_geometry = _page_geometry(width, height, _rotation_degrees(page))
            page_id = _deterministic_id(fingerprint, "page", page_index)
            spans = _extract_text_spans(
                page,
                page_id=page_id,
                raw_to_canonical=page_geometry.rawToCanonical,
                fingerprint=fingerprint,
                page_index=page_index,
                options=options,
            )
            images = _extract_images(
                page,
                page_id=page_id,
                raw_to_canonical=page_geometry.rawToCanonical,
                fingerprint=fingerprint,
                page_index=page_index,
            )
            objects.extend(spans)
            objects.extend(images)
            pages.append(
                generated.PhysicalPage(
                    id=page_id,
                    index=page_index,
                    geometry=page_geometry,
                    objectIds=[obj.id for obj in (*spans, *images)],
                )
            )
        metadata = generated.PhysicalMetadata(
            pageCount=len(pdf),
        )
        return generated.PhysicalDocument(
            schemaVersion="0.1.0",
            id=document_id,
            sourceFingerprint=fingerprint,
            pages=pages,
            objects=objects,
            metadata=metadata,
        )
    finally:
        pdf.close()


def write_physical_document(document: generated.PhysicalDocument, path: Path) -> dict[str, Any]:
    """Serialize for pipeline consumers and re-validate on load."""
    data = dump_document(document, path=path)
    load_document("physical-document", data)
    return data


def physical_document_from_bytes(data: bytes) -> generated.PhysicalDocument:
    """Load a PhysicalDocument from serialized bytes with validation."""
    document = load_document("physical-document", json.loads(data))
    return cast("generated.PhysicalDocument", document)
