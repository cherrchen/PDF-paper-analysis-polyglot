"""Tests for embedded-image extraction and source-bound figure resources."""

from __future__ import annotations

from pathlib import Path

import pytest
from document_model.generated import schema_models as generated
from pdf_pipeline.layout import recover_layout_document
from pdf_pipeline.physical import extract_physical_document
from pdf_pipeline.pipeline import region_texts_from
from pdf_pipeline.resource_store import (
    bind_figure_image_resources,
    extract_resource_document,
    figure_resource_ids,
)
from pdf_pipeline.semantic import recover_semantic_document

FIXTURE_DIR = Path(__file__).resolve().parents[4] / "tests/fixtures/source/latex/build"


def _fixture(name: str) -> bytes:
    path = FIXTURE_DIR / f"{name}.pdf"
    if not path.exists():
        pytest.skip(f"fixture PDF {name} not built; run `just latex-smoke`")
    return path.read_bytes()


@pytest.mark.unit
def test_extract_includes_png_bitmaps(tmp_path: Path) -> None:
    pdf_bytes = _fixture("figure-caption")
    resources = extract_resource_document(pdf_bytes, resource_dir=tmp_path)
    assert resources.resources.resources, "PNG raster images must be extracted"
    pngs = [record for record in resources.resources.resources if record.mediaType == "image/png"]
    assert pngs
    written = list(tmp_path.glob("*"))
    assert written


@pytest.mark.unit
def test_figure_resource_ids_do_not_guess_by_index() -> None:
    figure = generated.FigureContent(resources=generated.FigureResource(embeddedImageIds=[]))
    store = generated.ResourceStore(
        resources=[
            generated.ResourceRecord(
                id="00000000-0000-0000-0000-000000000001",
                kind="EMBEDDED_IMAGE",
                mediaType="image/png",
                origin="EXTRACTED",
            )
        ]
    )
    del store
    assert figure_resource_ids(figure) == []


@pytest.mark.unit
def test_bind_figure_resources_uses_source_physical_ids(tmp_path: Path) -> None:
    pdf_bytes = _fixture("figure-caption")
    physical = extract_physical_document(pdf_bytes)
    layout = recover_layout_document(physical)
    semantic = recover_semantic_document(layout, region_texts_from(physical, layout))
    resources = extract_resource_document(pdf_bytes, resource_dir=tmp_path)
    bound = bind_figure_image_resources(semantic, layout, resources.resources)
    figure = next(node for node in bound.nodes if node.kind == "FIGURE")
    assert isinstance(figure.content, generated.FigureContent)
    ids = figure.content.resources.embeddedImageIds
    assert ids
    resource_ids = {record.id for record in resources.resources.resources}
    assert set(ids) <= resource_ids
    image_ids = {obj.id for obj in physical.objects if obj.objectType == "imageObject"}
    assert set(ids) <= image_ids
