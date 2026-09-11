"""Extract embedded PDF images into a ResourceDocument (M5 Phase 5.7)."""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

from document_model import stable_uuid
from document_model.generated import schema_models as generated

from pdf_pipeline.pdfium_image import ImageExtractError, extract_embedded_images

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
    for page_index, image_counter, extracted in extract_embedded_images(pdf_bytes):
        resource_id = stable_uuid(fingerprint, "image", page_index, image_counter)
        if isinstance(extracted, ImageExtractError) or not extracted.payload:
            issues.append(
                _extract_issue(
                    fingerprint,
                    resource_id,
                    page_index,
                    image_counter,
                    stage=(
                        extracted.stage if isinstance(extracted, ImageExtractError) else "empty"
                    ),
                    reason=(
                        extracted.reason
                        if isinstance(extracted, ImageExtractError)
                        else "empty image bytes"
                    ),
                )
            )
            continue
        extension = _extension_for_media_type(extracted.media_type)
        file_path = resource_dir / f"{resource_id}{extension}"
        file_path.write_bytes(extracted.payload)
        records.append(
            generated.ResourceRecord(
                id=resource_id,
                kind="EMBEDDED_IMAGE",
                mediaType=extracted.media_type,
                byteLength=len(extracted.payload),
                sha256=hashlib.sha256(extracted.payload).hexdigest(),
                origin="EXTRACTED",
            )
        )
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
    fingerprint: str,
    resource_id: str,
    page_index: int,
    image_counter: int,
    *,
    stage: str,
    reason: str,
) -> generated.Issue:
    return generated.Issue(
        id=stable_uuid(fingerprint, "issue", "image-extract", page_index, image_counter),
        category="PHYSICAL_EXTRACTION",
        severity="WARNING",
        producer=_PRODUCER,
        message=(f"embedded image on page {page_index} could not be extracted ({stage}: {reason})"),
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
