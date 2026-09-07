# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportAttributeAccessIssue=false
"""Phase 2.6 + M5 render-anchor recovery with multi-fragment support."""

from __future__ import annotations

import ctypes
from typing import TYPE_CHECKING

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c
from document_model.generated import schema_models as generated

from pdf_pipeline.ids import stable_uuid
from pdf_pipeline.render_latex import anchor_end_name

if TYPE_CHECKING:
    from pathlib import Path

ANCHOR_HIT_SIZE_PT = 12.0
# generic-academic.tex uses 25mm margins.
_MARGIN_PT = 25.0 * 72.0 / 25.4
_END_SUFFIX = ":end"


def _decode_names() -> str:
    return "utf-16-le"


def recover_render_anchors(
    target_pdf: bytes | Path, semantic: generated.SemanticDocument
) -> list[generated.RenderAnchor]:
    """Recover per-node target regions from named destinations.

    Start and end hypertargets bound a content region. Same-page nodes become
    one rectangle covering the text; cross-page nodes emit one fragment per
    page spanning the content area, not just 12pt hit boxes at the endpoints.
    """
    path = target_pdf if isinstance(target_pdf, bytes | str) else str(target_pdf)
    pdf = pdfium.PdfDocument(path)
    try:
        page_sizes = [page.get_size() for page in pdf]
        node_ids = {node.id for node in semantic.nodes}
        points: dict[str, tuple[int, float, float]] = {}
        total = pdfium_c.FPDF_CountNamedDests(pdf.raw)
        for index in range(total):
            name, page_index, x, y = _read_named_dest(pdf, index, [size[1] for size in page_sizes])
            if name is None:
                continue
            base_id = name.removesuffix(_END_SUFFIX)
            if base_id not in node_ids:
                continue
            points[name] = (page_index, x, y)

        anchors: list[generated.RenderAnchor] = []
        for node_id in sorted(node_ids):
            start = points.get(node_id)
            end = points.get(anchor_end_name(node_id))
            fragments = _fragments_between(start, end, page_sizes)
            if not fragments:
                continue
            anchors.append(
                generated.RenderAnchor(
                    id=node_id,
                    semanticNodeId=node_id,
                    fragments=fragments,
                    confidence=0.9,
                )
            )
        return anchors
    finally:
        pdf.close()


def _fragments_between(
    start: tuple[int, float, float] | None,
    end: tuple[int, float, float] | None,
    page_sizes: list[tuple[float, float]],
) -> list[generated.PDFRenderFragment]:
    if start is None and end is None:
        return []
    if start is None:
        return [_point_fragment(end)] if end is not None else []
    if end is None:
        return [_point_fragment(start)]
    start_page, start_x, start_y = start
    end_page, end_x, end_y = end
    if start_page > end_page:
        start_page, end_page = end_page, start_page
        start_x, end_x = end_x, start_x
        start_y, end_y = end_y, start_y
    fragments: list[generated.PDFRenderFragment] = []
    for page_index in range(start_page, end_page + 1):
        width, height = page_sizes[page_index]
        left = min(start_x, end_x, _MARGIN_PT)
        left = max(0.0, left)
        frag_width = max(width - left - _MARGIN_PT, ANCHOR_HIT_SIZE_PT)
        if start_page == end_page:
            top = min(start_y, end_y)
            bottom = max(start_y, end_y) + ANCHOR_HIT_SIZE_PT
            frag_height = max(bottom - top, ANCHOR_HIT_SIZE_PT)
            fragments.append(_rect_fragment(page_index, left, top, frag_width, frag_height))
            continue
        if page_index == start_page:
            top = start_y
            frag_height = max(height - _MARGIN_PT - top, ANCHOR_HIT_SIZE_PT)
        elif page_index == end_page:
            top = _MARGIN_PT
            frag_height = max(end_y + ANCHOR_HIT_SIZE_PT - top, ANCHOR_HIT_SIZE_PT)
        else:
            top = _MARGIN_PT
            frag_height = max(height - 2 * _MARGIN_PT, ANCHOR_HIT_SIZE_PT)
        fragments.append(_rect_fragment(page_index, left, top, frag_width, frag_height))
    return fragments


def _read_named_dest(
    pdf: pdfium.PdfDocument, index: int, page_heights: list[float]
) -> tuple[str | None, int, float, float]:
    buffer_length = ctypes.c_long(0)
    dest = pdfium_c.FPDF_GetNamedDest(pdf.raw, index, None, ctypes.byref(buffer_length))
    if dest is None or buffer_length.value <= 0:
        return None, 0, 0.0, 0.0
    buffer = ctypes.create_string_buffer(buffer_length.value)
    pdfium_c.FPDF_GetNamedDest(
        pdf.raw,
        index,
        ctypes.cast(buffer, ctypes.c_void_p),
        ctypes.byref(buffer_length),
    )
    name = (
        buffer.raw[: buffer_length.value].decode(_decode_names(), errors="replace").rstrip("\x00")
    )
    page_index = pdfium_c.FPDFDest_GetDestPageIndex(pdf.raw, dest)
    if not 0 <= page_index < len(page_heights):
        return name, 0, 0.0, 0.0
    is_user_unit = ctypes.c_int()
    has_xy = ctypes.c_int()
    has_zoom = ctypes.c_int()
    x = ctypes.c_float()
    y = ctypes.c_float()
    zoom = ctypes.c_float()
    pdfium_c.FPDFDest_GetLocationInPage(
        dest,
        ctypes.byref(is_user_unit),
        ctypes.byref(has_xy),
        ctypes.byref(has_zoom),
        ctypes.byref(x),
        ctypes.byref(y),
        ctypes.byref(zoom),
    )
    point_y = page_heights[page_index] - y.value
    return name, page_index, x.value, point_y


def _point_fragment(point: tuple[int, float, float]) -> generated.PDFRenderFragment:
    page_index, x, y = point
    return _rect_fragment(page_index, x, y, ANCHOR_HIT_SIZE_PT, ANCHOR_HIT_SIZE_PT)


def _rect_fragment(
    page_index: int, x: float, y: float, width: float, height: float
) -> generated.PDFRenderFragment:
    return generated.PDFRenderFragment(
        pageIndex=page_index,
        geometry=generated.Rect(
            kind="rect",
            x=round(x, 2),
            y=round(y, 2),
            width=round(width, 2),
            height=round(height, 2),
        ),
    )


def build_mapping_bundle(
    semantic: generated.SemanticDocument,
    *,
    source_anchors: list[generated.SourceAnchor],
    source_semantic_bindings: list[generated.SourceSemanticBinding],
    physical_layout_bindings: list[generated.PhysicalLayoutBinding],
    render_anchors: list[generated.RenderAnchor],
    render_document_id: str,
) -> generated.MappingBundle:
    render_binding = generated.RenderBinding(
        id=stable_uuid(semantic.id, "render-binding"),
        renderDocumentId=render_document_id,
        renderAnchorIds=[anchor.id for anchor in render_anchors],
    )
    return generated.MappingBundle(
        schemaVersion="0.1.0",
        id=stable_uuid(semantic.id, "mapping-document"),
        physicalLayoutBindings=physical_layout_bindings,
        sourceAnchors=source_anchors,
        sourceSemanticBindings=source_semantic_bindings,
        renderBindings=[render_binding],
    )
