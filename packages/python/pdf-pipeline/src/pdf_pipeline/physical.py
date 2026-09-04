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
from typing import TYPE_CHECKING, cast

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c
from document_model import dump_document, load_document
from document_model.generated import schema_models as generated

from pdf_pipeline.ids import stable_uuid

if TYPE_CHECKING:
    from pathlib import Path

PRODUCER = "pdf-pipeline.physical"
PRODUCER_VERSION = "0.1.0"

# pypdfium2 reports PDF device coordinates with origin bottom-left. The
# canonical page space is origin top-left, y down, so canonical geometry is
# derived per page with: canonical_y = page_height - raw_bottom - raw_height.
RAW_TO_CANONICAL = generated.Matrix(a=1.0, b=0.0, c=0.0, d=-1.0, e=0.0, f=0.0)
CANONICAL_TO_RAW = generated.Matrix(a=1.0, b=0.0, c=0.0, d=-1.0, e=0.0, f=0.0)


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
    rotation = page.get_rotation()
    value = {0: 0, 1: 90, 2: 180, 3: 270}[rotation]
    return cast("generated.PageRotation", value)


def _canonical_rect(
    left: float, bottom: float, right: float, top: float, page_height: float
) -> generated.Rect:
    x = min(left, right)
    width = abs(right - left)
    height = abs(top - bottom)
    y = page_height - max(top, bottom)
    return generated.Rect(kind="rect", x=x, y=y, width=width, height=height)


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
    page_height: float,
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
                    geometry=_canonical_rect(left, bottom, right, top, page_height),
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
    page_height: float,
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
                geometry=_canonical_rect(left, bottom, right, top, page_height),
            )
        )
        image_counter += 1
    return objects


def _page_geometry(
    width: float, height: float, rotation: generated.PageRotation
) -> generated.PageGeometry:
    return generated.PageGeometry(
        widthPt=width,
        heightPt=height,
        rotation=rotation,
        rawToCanonical=RAW_TO_CANONICAL,
        canonicalToRaw=CANONICAL_TO_RAW,
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
            page_id = _deterministic_id(fingerprint, "page", page_index)
            spans = _extract_text_spans(
                page,
                page_id=page_id,
                page_height=height,
                fingerprint=fingerprint,
                page_index=page_index,
                options=options,
            )
            images = _extract_images(
                page,
                page_id=page_id,
                page_height=height,
                fingerprint=fingerprint,
                page_index=page_index,
            )
            objects.extend(spans)
            objects.extend(images)
            pages.append(
                generated.PhysicalPage(
                    id=page_id,
                    index=page_index,
                    geometry=_page_geometry(width, height, _rotation_degrees(page)),
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


def write_physical_document(document: generated.PhysicalDocument, path: Path) -> dict:
    """Serialize for pipeline consumers and re-validate on load."""
    data = dump_document(document, path=path)
    load_document("physical-document", data)
    return data


def physical_document_from_bytes(data: bytes) -> generated.PhysicalDocument:
    """Load a PhysicalDocument from serialized bytes with validation."""
    document = load_document("physical-document", json.loads(data))
    return cast("generated.PhysicalDocument", document)
