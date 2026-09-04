"""Phase 2.2 minimal layout recovery tests.

Covers Roadmap M2 Phase 2.2: TextRegion, Heading-like regions, Figure
regions, basic two-column detection, and a valid reading flow graph.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest
from document_model import dump_document, load_document, validate_layer_separation
from document_model.generated import schema_models as generated
from pdf_pipeline.layout import recover_layout_document, split_columns
from pdf_pipeline.physical import extract_physical_document

FIXTURE_DIR = Path(__file__).resolve().parents[4] / "tests/fixtures/source/latex/build"
EXTERNAL_DIR = Path(__file__).resolve().parents[4] / "tests/fixtures/external/papers"


def _fixture(name: str, directory: Path = FIXTURE_DIR) -> bytes:
    path = directory / f"{name}.pdf"
    if not path.exists():
        pytest.skip(f"fixture PDF {name} not available")
    return path.read_bytes()


def test_smoke_layout_valid_and_deterministic() -> None:
    data = _fixture("smoke")
    physical = extract_physical_document(data)
    layout = recover_layout_document(physical)
    data_out = dump_document(layout)

    load_document("layout-document", data_out)
    assert validate_layer_separation(dump_document(physical), data_out) == []
    assert recover_layout_document(extract_physical_document(data)) == layout


def test_heading_like_detected_on_smoke_title() -> None:
    physical = extract_physical_document(_fixture("smoke"))
    layout = recover_layout_document(physical)
    heading_regions = [
        region
        for region in layout.regions
        if any(label.label == "HEADING_LIKE" for label in region.labels)
    ]
    assert heading_regions, "title span should be heading-like"


def test_two_column_detection_real_paper() -> None:
    physical = extract_physical_document(_fixture("arxiv-1810.04805", EXTERNAL_DIR))
    spans_by_page: dict[str, list[generated.TextSpan]] = {}
    for obj in physical.objects:
        if obj.objectType == "textSpan":
            spans_by_page.setdefault(obj.pageId, []).append(obj)
    page = physical.pages[1]
    two_column, split_x = split_columns(spans_by_page[page.id], page.geometry.widthPt)
    assert two_column
    assert page.geometry.widthPt * 0.4 < split_x < page.geometry.widthPt * 0.6


def test_single_column_detection_real_paper() -> None:
    physical = extract_physical_document(_fixture("arxiv-1706.03762", EXTERNAL_DIR))
    spans_by_page: dict[str, list[generated.TextSpan]] = {}
    for obj in physical.objects:
        if obj.objectType == "textSpan":
            spans_by_page.setdefault(obj.pageId, []).append(obj)
    page = physical.pages[1]
    two_column, _ = split_columns(spans_by_page[page.id], page.geometry.widthPt)
    assert not two_column


def test_reading_flow_is_linear_and_covers_all_regions() -> None:
    physical = extract_physical_document(_fixture("smoke"))
    layout = recover_layout_document(physical)
    assert set(layout.primaryFlow) == {region.id for region in layout.regions}
    assert layout.readingFlow.nodes == layout.primaryFlow
    assert len(layout.readingFlow.edges) == len(layout.regions) - 1


def test_regions_reference_physical_objects() -> None:
    physical = extract_physical_document(_fixture("smoke"))
    layout = recover_layout_document(physical)
    physical_ids = {obj.id for obj in physical.objects}
    for region in layout.regions:
        assert region.physicalObjectIds
        assert set(region.physicalObjectIds) <= physical_ids


def test_reading_flow_includes_figures_in_geometry_order() -> None:
    fixture = Path(__file__).resolve().parents[4] / (
        "schemas/fixtures/physical-document/two-page-two-column.valid.json"
    )
    physical = cast(
        "generated.PhysicalDocument",
        load_document("physical-document", json.loads(fixture.read_text())),
    )
    layout = recover_layout_document(physical)

    assert set(layout.primaryFlow) == {region.id for region in layout.regions}
    first_page = layout.pages[0]
    first_page_regions = {
        region.id: region for region in layout.regions if region.pageId == first_page.pageId
    }
    assert any(first_page_regions[region_id].kind == "FIGURE" for region_id in first_page.regionIds)

    def region_key(region: generated.LayoutRegion) -> tuple[float, float, str]:
        assert isinstance(region.geometry, generated.Rect)
        return (region.geometry.y, region.geometry.x, region.id)

    assert first_page.regionIds[0] == min(first_page_regions.values(), key=region_key).id
