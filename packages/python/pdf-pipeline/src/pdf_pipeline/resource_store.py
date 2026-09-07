# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportAttributeAccessIssue=false, reportCallIssue=false, reportPrivateUsage=false
"""Extract embedded PDF images into a ResourceDocument (M5 Phase 5.7)."""

from __future__ import annotations

import hashlib
import io
from typing import TYPE_CHECKING

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c
from document_model import stable_uuid
from document_model.generated import schema_models as generated

from pdf_pipeline.physical import _deterministic_id

if TYPE_CHECKING:
    from pathlib import Path


def extract_resource_document(
    pdf_bytes: bytes,
    *,
    resource_dir: Path,
) -> generated.ResourceDocument:
    """Extract embedded raster images and write them to ``resource_dir``."""
    fingerprint = hashlib.sha256(pdf_bytes).hexdigest()
    resource_dir.mkdir(parents=True, exist_ok=True)
    records: list[generated.ResourceRecord] = []
    pdf = pdfium.PdfDocument(pdf_bytes)
    try:
        for page_index, page in enumerate(pdf):
            image_counter = 0
            for obj in page.get_objects(max_depth=16):
                if obj.type != pdfium_c.FPDF_PAGEOBJ_IMAGE:
                    continue
                filters = obj.get_filters()
                if not any(name in filters for name in ("DCTDecode", "JPXDecode")):
                    continue
                extracted = _extract_image_bytes(obj)
                if extracted is None:
                    continue
                media_type, image_bytes = extracted
                if not image_bytes:
                    continue
                resource_id = _deterministic_id(fingerprint, "image", page_index, image_counter)
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
    return generated.ResourceDocument(
        schemaVersion="0.1.0",
        id=stable_uuid(fingerprint, "resource-document"),
        sourceFingerprint=fingerprint,
        resources=generated.ResourceStore(resources=records),
        provenanceIds=[],
    )


def resource_path(resource_dir: Path, record: generated.ResourceRecord) -> Path:
    extension = _extension_for_media_type(record.mediaType)
    return resource_dir / f"{record.id}{extension}"


def figure_resource_ids(
    figure: generated.FigureContent,
    resources: generated.ResourceStore,
    *,
    figure_index: int,
) -> list[str]:
    """Return stored resource ids backing a figure, in preference order."""
    ids = list(figure.resources.embeddedImageIds)
    if ids:
        return ids
    embedded = [record.id for record in resources.resources if record.kind == "EMBEDDED_IMAGE"]
    if figure_index < len(embedded):
        return [embedded[figure_index]]
    return embedded[:1]


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
    buffer = io.BytesIO()
    try:
        image_obj.extract(buffer)  # type: ignore[attr-defined]
    except (RuntimeError, OSError, TypeError, ValueError, AttributeError):
        return None
    payload = buffer.getvalue()
    if not payload:
        return None
    return _media_type_from_bytes(payload), payload


def _media_type_from_bytes(data: bytes) -> str:
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"RIFF") and b"WEBP" in data[:16]:
        return "image/webp"
    return "application/octet-stream"
