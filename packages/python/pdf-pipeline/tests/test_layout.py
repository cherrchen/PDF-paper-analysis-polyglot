"""M3 layout recovery tests (Roadmap Milestone 3).

Covers the full recovery chain on real fixture PDFs: evidence collection,
band/column structure, reading flow, caption groups, footnotes, schema
validity, layer separation, and determinism. Unit-level algorithm tests
live in test_evidence.py / test_fusion.py / test_bands.py /
test_reading_flow.py / test_captions.py / test_footnotes.py.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from document_model import dump_document, load_document, validate_layer_separation
from pdf_pipeline.evidence.providers import MockLayoutEvidenceProvider
from pdf_pipeline.layout import recover_layout_document
from pdf_pipeline.physical import extract_physical_document
from pdf_pipeline.pipeline import region_texts_from

if TYPE_CHECKING:
    from document_model.generated import schema_models as generated

FIXTURE_DIR = Path(__file__).resolve().parents[4] / "tests/fixtures/source/latex/build"
EXTERNAL_DIR = Path(__file__).resolve().parents[4] / "tests/fixtures/external/papers"


def _fixture(name: str, directory: Path = FIXTURE_DIR) -> bytes:
    path = directory / f"{name}.pdf"
    if not path.exists():
        pytest.skip(f"fixture PDF {name} not available")
    return path.read_bytes()


def _recover(
    data: bytes,
) -> tuple[generated.PhysicalDocument, generated.LayoutDocument]:
    physical = extract_physical_document(data)
    evidence = MockLayoutEvidenceProvider().collect(physical)
    return physical, recover_layout_document(physical, evidence=evidence)


def test_layout_valid_layer_separated_and_deterministic() -> None:
    data = _fixture("smoke")
    physical, layout = _recover(data)
    layout_data = dump_document(layout)
    load_document("layout-document", layout_data)
    assert validate_layer_separation(dump_document(physical), layout_data) == []
    assert dump_document(_recover(data)[1]) == layout_data


def test_two_column_fixture_recovers_multicolumn_band() -> None:
    _, layout = _recover(_fixture("two-column"))
    assert any(
        band.layoutMode == "MULTI_COLUMN" and len(band.columnIds) == 2 for band in layout.bands
    )


def test_mixed_bands_and_spanning_figure_fixtures_are_multicolumn() -> None:
    for name in ("mixed-bands", "spanning-figure", "footnote-multicolumn"):
        _, layout = _recover(_fixture(name))
        assert any(
            band.layoutMode == "MULTI_COLUMN" and len(band.columnIds) == 2 for band in layout.bands
        ), f"{name} must recover a two-column band"


def test_page_numbers_leave_primary_flow() -> None:
    physical, layout = _recover(_fixture("two-column"))
    texts = region_texts_from(physical, layout)
    footers = [region for region in layout.regions if region.kind == "FOOTER"]
    assert footers, "page number must be recovered as FOOTER"
    for footer in footers:
        assert footer.id not in layout.primaryFlow
        assert (
            texts.get(footer.id, "").strip().isdigit() or len(texts.get(footer.id, "").strip()) <= 4
        )


def test_fused_regions_link_provenance_records() -> None:
    _, layout = _recover(_fixture("smoke"))
    linked = [region for region in layout.regions if region.provenanceIds]
    assert linked, "fusion provenance must be attached to regions"
    record_ids = {record.id for record in layout.provenance.records}
    for region in linked:
        assert set(region.provenanceIds) <= record_ids


def test_smoke_title_is_heading_like() -> None:
    _, layout = _recover(_fixture("smoke"))
    heading_regions = [
        region
        for region in layout.regions
        if any(label.label == "HEADING_LIKE" for label in region.labels)
    ]
    assert heading_regions, "title span should be heading-like"


@pytest.mark.slow
def test_two_column_real_paper_body_is_multicolumn() -> None:
    physical, layout = _recover(_fixture("arxiv-1810.04805", EXTERNAL_DIR))
    pages = {page.id: page.index for page in physical.pages}
    page1_bands = [band for band in layout.bands if pages[band.pageId] == 1]
    assert page1_bands, "external paper must have bands on page 1"
    multicolumn = [band for band in page1_bands if band.layoutMode == "MULTI_COLUMN"]
    assert multicolumn, "two-column body must produce MULTI_COLUMN bands"
    for band in multicolumn:
        assert len(band.columnIds) == 2
    title_bands = [band for band in layout.bands if pages[band.pageId] == 0]
    assert any(band.layoutMode == "FULL_WIDTH" for band in title_bands)


@pytest.mark.slow
def test_single_column_real_paper_stays_single_column() -> None:
    physical, layout = _recover(_fixture("arxiv-1706.03762", EXTERNAL_DIR))
    pages = {page.id: page.index for page in physical.pages}
    body_bands = [band for band in layout.bands if pages[band.pageId] == 1]
    assert body_bands
    assert all(band.layoutMode != "MULTI_COLUMN" for band in body_bands)


def test_reading_flow_covers_all_regions_with_reasoned_edges() -> None:
    _, layout = _recover(_fixture("smoke"))
    assert set(layout.readingFlow.nodes) == {region.id for region in layout.regions}
    valid_reasons = {
        "SAME_COLUMN",
        "NEXT_COLUMN",
        "AFTER_SPANNING_BLOCK",
        "BEFORE_SPANNING_BLOCK",
        "CAPTION_ASSOCIATION",
        "CONTINUATION",
        "FOOTNOTE_FLOW",
    }
    for edge in layout.readingFlow.edges:
        assert edge.reason in valid_reasons
        assert 0.0 <= edge.confidence <= 1.0
    # Primary flow is a subset: furniture and footnotes stay out.
    region_kinds = {region.id: region.kind for region in layout.regions}
    assert set(layout.primaryFlow) <= set(layout.readingFlow.nodes)
    for region_id in layout.primaryFlow:
        assert region_kinds[region_id] not in {"FOOTNOTE", "HEADER", "FOOTER"}


def test_footnotes_leave_primary_flow() -> None:
    _, layout = _recover(_fixture("footnote-multicolumn"))
    footnotes = [region for region in layout.regions if region.kind == "FOOTNOTE"]
    assert footnotes, "footnote fixture must recover footnote regions"
    for footnote in footnotes:
        assert footnote.id not in layout.primaryFlow


def test_caption_group_recovered_on_figure_caption_fixture() -> None:
    _, layout = _recover(_fixture("figure-caption"))
    figure_blocks = [group for group in layout.groups if group.kind == "FIGURE_BLOCK"]
    assert len(figure_blocks) == 1
    members = {region.id: region for region in layout.regions}
    group = figure_blocks[0]
    kinds = sorted(members[member].kind for member in group.memberIds)
    assert kinds == ["FIGURE", "TEXT"]


def test_spanning_figure_band() -> None:
    _, layout = _recover(_fixture("spanning-figure"))
    assert any(band.layoutMode == "SPANNING" for band in layout.bands)


def test_column_regions_partition_page_regions() -> None:
    _, layout = _recover(_fixture("mixed-bands"))
    column_members = [rid for column in layout.columns for rid in column.regionIds]
    assert len(column_members) == len(set(column_members))
