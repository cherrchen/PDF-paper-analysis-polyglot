# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportAttributeAccessIssue=false, reportCallIssue=false, reportPrivateUsage=false
"""Extract embedded PDF images into a ResourceDocument (M5 Phase 5.7)."""

from __future__ import annotations

import hashlib
import io
import struct
import zlib
from typing import TYPE_CHECKING

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c
from document_model import stable_uuid
from document_model.generated import schema_models as generated

from pdf_pipeline.physical import _deterministic_id

if TYPE_CHECKING:
    from pathlib import Path

_PRODUCER = "pdf-pipeline.resource-store"


def extract_resource_document(
    pdf_bytes: bytes,
    *,
    resource_dir: Path,
) -> generated.ResourceDocument:
    """Extract embedded raster images and write them to ``resource_dir``.

    Resource IDs use the same deterministic scheme as physical ``imageObject``
    IDs so figures can bind by source physicalObjectIds rather than by order.
    """
    fingerprint = hashlib.sha256(pdf_bytes).hexdigest()
    resource_dir.mkdir(parents=True, exist_ok=True)
    records: list[generated.ResourceRecord] = []
    issues: list[generated.Issue] = []
    pdf = pdfium.PdfDocument(pdf_bytes)
    try:
        for page_index, page in enumerate(pdf):
            image_counter = 0
            for obj in page.get_objects(max_depth=16):
                if obj.type != pdfium_c.FPDF_PAGEOBJ_IMAGE:
                    continue
                left, bottom, right, top = obj.get_pos()
                if right - left <= 0 or top - bottom <= 0:
                    continue
                resource_id = _deterministic_id(fingerprint, "image", page_index, image_counter)
                extracted = _extract_image_bytes(obj)
                if extracted is None:
                    issues.append(
                        _extract_issue(
                            fingerprint,
                            resource_id,
                            page_index,
                            image_counter,
                        )
                    )
                    image_counter += 1
                    continue
                media_type, image_bytes = extracted
                if not image_bytes:
                    issues.append(
                        _extract_issue(
                            fingerprint,
                            resource_id,
                            page_index,
                            image_counter,
                        )
                    )
                    image_counter += 1
                    continue
                extension = _extension_for_media_type(media_type)
                file_path = resource_dir / f"{resource_id}{extension}"
                file_path.write_bytes(image_bytes)
                records.append(
                    generated.ResourceRecord(
                        id=resource_id,
                        kind="EMBEDDED_IMAGE",
                        mediaType=media_type,
                        byteLength=len(image_bytes),
                        sha256=hashlib.sha256(image_bytes).hexdigest(),
                        origin="EXTRACTED",
                    )
                )
                image_counter += 1
    finally:
        pdf.close()
    document = generated.ResourceDocument(
        schemaVersion="0.1.0",
        id=stable_uuid(fingerprint, "resource-document"),
        sourceFingerprint=fingerprint,
        resources=generated.ResourceStore(resources=records),
        provenanceIds=[],
    )
    if issues:
        return document.model_copy(update={"issues": generated.IssueStore(issues=issues)})
    return document


def resource_path(resource_dir: Path, record: generated.ResourceRecord) -> Path:
    extension = _extension_for_media_type(record.mediaType)
    return resource_dir / f"{record.id}{extension}"


def figure_resource_ids(figure: generated.FigureContent) -> list[str]:
    """Return stored resource ids bound on the figure. Never guess by index."""
    return list(figure.resources.embeddedImageIds)


def bind_figure_image_resources(
    semantic: generated.SemanticDocument,
    layout: generated.LayoutDocument,
    resources: generated.ResourceStore,
) -> generated.SemanticDocument:
    """Copy ResourceIDs onto figures whose layout regions contain those images."""
    resource_ids = {record.id for record in resources.resources if record.kind == "EMBEDDED_IMAGE"}
    if not resource_ids:
        return semantic
    regions = {region.id: region for region in layout.regions}
    nodes: list[generated.SemanticNode] = []
    changed = False
    for node in semantic.nodes:
        if node.kind != "FIGURE" or not isinstance(node.content, generated.FigureContent):
            nodes.append(node)
            continue
        bound: list[str] = []
        raw_regions = node.attributes.get("layoutRegionIds")
        region_ids = [item for item in raw_regions if isinstance(item, str)] if raw_regions else []
        for region_id in region_ids:
            region = regions.get(region_id)
            if region is None:
                continue
            for object_id in region.physicalObjectIds:
                if object_id in resource_ids and object_id not in bound:
                    bound.append(object_id)
        if bound == list(node.content.resources.embeddedImageIds):
            nodes.append(node)
            continue
        content = node.content.model_copy(
            update={"resources": generated.FigureResource(embeddedImageIds=bound)}
        )
        nodes.append(node.model_copy(update={"content": content}))
        changed = True
    if not changed:
        return semantic
    return semantic.model_copy(update={"nodes": nodes})


def _extract_issue(
    fingerprint: str, resource_id: str, page_index: int, image_counter: int
) -> generated.Issue:
    return generated.Issue(
        id=stable_uuid(fingerprint, "issue", "image-extract", page_index, image_counter),
        category="PHYSICAL_EXTRACTION",
        severity="WARNING",
        producer=_PRODUCER,
        message=f"embedded image on page {page_index} could not be extracted",
        affectedIds=[resource_id],
        recoverable=True,
        fallback="empty figure box",
    )


def _extension_for_media_type(media_type: str) -> str:
    mapping = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/webp": ".webp",
    }
    return mapping.get(media_type.lower(), ".bin")


def _extract_image_bytes(image_obj: object) -> tuple[str, bytes] | None:
    """Return media type and bytes for an embedded image, or None when unsupported."""
    extracted = _extract_native_image(image_obj)
    if extracted is not None:
        return extracted
    return _extract_bitmap_png(image_obj)


def _extract_native_image(image_obj: object) -> tuple[str, bytes] | None:
    buffer = io.BytesIO()
    try:
        image_obj.extract(buffer)  # type: ignore[attr-defined]
    except (RuntimeError, OSError, TypeError, ValueError, AttributeError):
        return None
    payload = buffer.getvalue()
    if not payload:
        return None
    media_type = _media_type_from_bytes(payload)
    if media_type == "application/octet-stream":
        return None
    return media_type, payload


def _extract_bitmap_png(image_obj: object) -> tuple[str, bytes] | None:
    bitmap = None
    png: bytes | None = None
    try:
        try:
            bitmap = image_obj.get_bitmap(render=True)  # type: ignore[attr-defined]
        except Exception:
            bitmap = image_obj.get_bitmap()  # type: ignore[attr-defined]
        png = _bitmap_to_png(bitmap)
    except Exception:
        return None
    finally:
        if bitmap is not None:
            close = getattr(bitmap, "close", None)
            if callable(close):
                close()
    if not png:
        return None
    return "image/png", png


def _bitmap_to_png(bitmap: object) -> bytes | None:
    width = int(bitmap.width)  # type: ignore[attr-defined]
    height = int(bitmap.height)  # type: ignore[attr-defined]
    stride = int(bitmap.stride)  # type: ignore[attr-defined]
    channels = int(bitmap.n_channels)  # type: ignore[attr-defined]
    mode = str(bitmap.mode)  # type: ignore[attr-defined]
    raw = bytes(bitmap.buffer)  # type: ignore[attr-defined]
    color_type, out_channels, swap_bgr = _png_layout(mode, channels)
    if color_type is None or out_channels is None:
        return None
    rows: list[bytes] = []
    row_bytes = width * channels
    for y in range(height):
        start = y * stride
        row = bytearray(raw[start : start + row_bytes])
        if swap_bgr:
            for index in range(0, len(row), channels):
                row[index], row[index + 2] = row[index + 2], row[index]
        rows.append(b"\x00" + bytes(row[: width * out_channels]))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, color_type, 0, 0, 0)
    idat = zlib.compress(b"".join(rows), 9)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", idat)
        + _png_chunk(b"IEND", b"")
    )


def _png_layout(mode: str, channels: int) -> tuple[int | None, int | None, bool]:
    if mode in {"L", "Gray"} or channels == 1:
        return 0, 1, False
    if mode == "BGR":
        return 2, 3, True
    if mode == "RGB" or channels == 3:
        return 2, 3, False
    if mode == "BGRA":
        return 6, 4, True
    if mode == "RGBA" or channels == 4:
        return 6, 4, False
    return None, None, False


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    checksum = zlib.crc32(tag)
    checksum = zlib.crc32(data, checksum) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", checksum)


def _media_type_from_bytes(data: bytes) -> str:
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"RIFF") and b"WEBP" in data[:16]:
        return "image/webp"
    return "application/octet-stream"
