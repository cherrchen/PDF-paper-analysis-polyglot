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
_END_SUFFIX = ":end"


def _decode_names() -> str:
    return "utf-16-le"


def recover_render_anchors(
    target_pdf: bytes | Path, semantic: generated.SemanticDocument
) -> list[generated.RenderAnchor]:
    """Recover per-node target regions from named destinations."""
    path = target_pdf if isinstance(target_pdf, bytes | str) else str(target_pdf)
    pdf = pdfium.PdfDocument(path)
    try:
        page_heights = [page.get_size()[1] for page in pdf]
        node_ids = {node.id for node in semantic.nodes}
        points: dict[str, tuple[int, float, float]] = {}
        total = pdfium_c.FPDF_CountNamedDests(pdf.raw)
        for index in range(total):
            name, page_index, x, y = _read_named_dest(pdf, index, page_heights)
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
            if start is None and end is None:
                continue
            fragments: list[generated.PDFRenderFragment] = []
            if start is not None:
                fragments.append(_fragment(start))
            if end is not None:
                fragments.append(_fragment(end))
            if not fragments and start is not None:
                fragments.append(_fragment(start))
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


def _fragment(point: tuple[int, float, float]) -> generated.PDFRenderFragment:
    page_index, x, y = point
    return generated.PDFRenderFragment(
        pageIndex=page_index,
        geometry=generated.Rect(
            kind="rect",
            x=round(x, 2),
            y=round(y, 2),
            width=ANCHOR_HIT_SIZE_PT,
            height=ANCHOR_HIT_SIZE_PT,
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
