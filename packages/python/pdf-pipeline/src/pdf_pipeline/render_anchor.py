# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportAttributeAccessIssue=false
"""Phase 2.6 render-anchor recovery: target PDF named dests -> MappingBundle.

The projection embeds ``\\renderanchor{<nodeId>}`` (a hyperref hypertarget)
per semantic node. After LuaLaTeX compilation each hypertarget becomes a PDF
named destination; this module reads those destinations back with PDFium and
writes RenderBinding/RenderAnchor entries into the canonical MappingBundle,
completing SourceAnchor <-> SemanticNode <-> RenderAnchor.
"""

from __future__ import annotations

import ctypes
from typing import TYPE_CHECKING

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c
from document_model.generated import schema_models as generated

from pdf_pipeline.ids import stable_uuid

if TYPE_CHECKING:
    from pathlib import Path

_UUID_SHAPE = "-"
ANCHOR_HIT_SIZE_PT = 12.0


def _decode_names() -> str:
    return "utf-16-le"


def recover_render_anchors(
    target_pdf: bytes | Path, semantic: generated.SemanticDocument
) -> list[generated.RenderAnchor]:
    """Recover per-node target regions from named destinations.

    PDFium reports destination coordinates in PDF user space (origin
    bottom-left). The schema's render fragments use the same canonical page
    space as the physical layer (origin top-left, y down), so y is flipped
    with the page height.
    """
    path = target_pdf if isinstance(target_pdf, bytes | str) else str(target_pdf)
    pdf = pdfium.PdfDocument(path)
    try:
        page_heights = [page.get_size()[1] for page in pdf]
        node_ids = {node.id for node in semantic.nodes}
        anchors: list[generated.RenderAnchor] = []
        total = pdfium_c.FPDF_CountNamedDests(pdf.raw)
        for index in range(total):
            buffer_length = ctypes.c_long(0)
            dest = pdfium_c.FPDF_GetNamedDest(pdf.raw, index, None, ctypes.byref(buffer_length))
            if dest is None or buffer_length.value <= 0:
                continue
            buffer = ctypes.create_string_buffer(buffer_length.value)
            pdfium_c.FPDF_GetNamedDest(
                pdf.raw,
                index,
                ctypes.cast(buffer, ctypes.c_void_p),
                ctypes.byref(buffer_length),
            )
            name = (
                buffer.raw[: buffer_length.value]
                .decode(_decode_names(), errors="replace")
                .rstrip("\x00")
            )
            if name not in node_ids:
                continue
            page_index = pdfium_c.FPDFDest_GetDestPageIndex(pdf.raw, dest)
            if not 0 <= page_index < len(page_heights):
                continue
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
            anchors.append(
                generated.RenderAnchor(
                    # The anchor id is the node id itself: the named dest name
                    # IS the SemanticNode id, keeping identity trivially stable.
                    id=name,
                    semanticNodeId=name,
                    fragments=[
                        generated.PDFRenderFragment(
                            pageIndex=page_index,
                            geometry=generated.Rect(
                                kind="rect",
                                x=round(x.value, 2),
                                y=round(point_y, 2),
                                width=ANCHOR_HIT_SIZE_PT,
                                height=ANCHOR_HIT_SIZE_PT,
                            ),
                        )
                    ],
                    confidence=0.9,
                )
            )
        return anchors
    finally:
        pdf.close()


def build_mapping_bundle(
    semantic: generated.SemanticDocument,
    *,
    source_anchors: list[generated.SourceAnchor],
    source_semantic_bindings: list[generated.SourceSemanticBinding],
    physical_layout_bindings: list[generated.PhysicalLayoutBinding],
    render_anchors: list[generated.RenderAnchor],
    render_document_id: str,
) -> generated.MappingBundle:
    """Assemble the canonical MappingBundle with all three anchor families."""
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
