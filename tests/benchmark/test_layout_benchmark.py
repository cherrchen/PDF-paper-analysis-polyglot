"""M3 layout benchmark: recovered layout vs hand-derived ground truth.

Ground truth lives in ``tests/fixtures/layout-truth/<fixture>.json`` and is
derived from the fixture's LaTeX source (visual reading order, captions,
footnote expectations, band/column invariants). Metrics follow Roadmap M3
Validation: Region Recall, pairwise ordering accuracy, sequence accuracy.

Band/Column stability (M3 Exit Gate) is asserted through the per-page
``singleColumnOnly`` / ``expectSpanningBand`` flags plus structural
invariants; exact band-mode sequences are intentionally not pinned (the
XY-cut fragments bands at display gaps, which is structure-preserving but
not worth pinning byte-for-byte).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from document_model import dump_document, load_document, validate_layer_separation
from document_model.generated import schema_models as generated
from pdf_pipeline.evidence.providers import MockLayoutEvidenceProvider
from pdf_pipeline.layout import recover_layout_document
from pdf_pipeline.metrics import order_metrics
from pdf_pipeline.physical import extract_physical_document
from pdf_pipeline.pipeline import region_texts_from

if TYPE_CHECKING:
    from document_model.generated import schema_models as generated
    from document_model.generated.schema_models import LayoutDocument, PhysicalDocument

ROOT = Path(__file__).resolve().parents[2]
BUILD_DIR = ROOT / "tests/fixtures/source/latex/build"
TRUTH_DIR = ROOT / "tests/fixtures/layout-truth"

# Exit-gate thresholds (Roadmap M3).
MIN_REGION_RECALL = 0.9
MIN_PAIRWISE_ACCURACY = 0.95

TRUTH_FILES = sorted(TRUTH_DIR.glob("*.json"))


TRUTHS = [json.loads(path.read_text()) for path in TRUTH_FILES]


@pytest.mark.parametrize("truth", TRUTHS, ids=lambda t: t["fixture"])
def test_layout_benchmark(truth: dict[str, Any]) -> None:
    fixture = truth["fixture"]
    pdf_path = BUILD_DIR / f"{fixture}.pdf"
    if not pdf_path.exists():
        pytest.skip(f"fixture PDF {fixture} not built; run `just latex-smoke`")
    data = pdf_path.read_bytes()

    physical = extract_physical_document(data)
    evidence = MockLayoutEvidenceProvider().collect(physical)
    layout = recover_layout_document(physical, evidence=evidence)
    layout_data = dump_document(layout)
    load_document("layout-document", layout_data)
    assert validate_layer_separation(dump_document(physical), layout_data) == []
    # Determinism is part of stability.
    assert (
        dump_document(recover_layout_document(extract_physical_document(data), evidence=evidence))
        == layout_data
    )

    _assert_band_structure(truth, physical, layout)
    _assert_reading_order(truth, physical, layout)
    _assert_captions(truth, physical, layout)
    _assert_footnotes(truth, layout)


def _assert_band_structure(
    truth: dict[str, Any],
    physical: PhysicalDocument,
    layout: LayoutDocument,
) -> None:
    pages = {page.id: page.index for page in physical.pages}
    bands_by_page: dict[int, list[generated.PageBand]] = {}
    for band in layout.bands:
        bands_by_page.setdefault(pages[band.pageId], []).append(band)

    for page_truth in truth.get("pages", []):
        index = page_truth["pageIndex"]
        bands = bands_by_page.get(index, [])
        if page_truth.get("singleColumnOnly"):
            assert all(len(band.columnIds) == 1 for band in bands), (
                f"{truth['fixture']} page {index}: expected single-column bands"
            )
        if page_truth.get("expectSpanningBand"):
            assert any(band.layoutMode == "SPANNING" for band in bands), (
                f"{truth['fixture']} page {index}: expected a SPANNING band"
            )

    # Structural invariants: every region lives in exactly one column, and
    # bands are y-ordered per page.
    column_members = [region_id for column in layout.columns for region_id in column.regionIds]
    assert len(column_members) == len(set(column_members))
    for index, bands in bands_by_page.items():
        y_starts = [band.yStart for band in bands]
        assert y_starts == sorted(y_starts), f"{truth['fixture']} page {index}: bands out of order"


def _assert_reading_order(
    truth: dict[str, Any],
    physical: PhysicalDocument,
    layout: LayoutDocument,
) -> None:
    texts = region_texts_from(physical, layout)
    metrics = order_metrics(truth["readingOrder"], layout.primaryFlow, texts)
    assert metrics.region_recall >= MIN_REGION_RECALL, (
        f"{truth['fixture']}: region recall {metrics.region_recall} below {MIN_REGION_RECALL}"
    )
    assert metrics.pairwise_ordering_accuracy >= MIN_PAIRWISE_ACCURACY, (
        f"{truth['fixture']}: pairwise ordering {metrics.pairwise_ordering_accuracy}"
    )
    assert metrics.sequence_accuracy, f"{truth['fixture']}: reading sequence mismatch"

    if truth.get("expectCrossPageContinuation"):
        continuation_targets = {
            edge.target for edge in layout.readingFlow.edges if edge.reason == "CONTINUATION"
        }
        assert continuation_targets, f"{truth['fixture']}: no continuation evidence"


def _assert_captions(
    truth: dict[str, Any],
    physical: PhysicalDocument,
    layout: LayoutDocument,
) -> None:
    expected = truth.get("captions", [])
    if not expected:
        return
    texts = region_texts_from(physical, layout)
    regions = {region.id: region for region in layout.regions}
    for caption_truth in expected:
        found = False
        for group in layout.groups:
            if group.kind != caption_truth["kind"] or len(group.memberIds) != 2:
                continue
            members = [regions[member] for member in group.memberIds]
            caption = next((region for region in members if region.kind == "TEXT"), None)
            if caption is not None and caption_truth["prefix"] in texts.get(caption.id, ""):
                found = True
                break
        assert found, f"{truth['fixture']}: caption {caption_truth['prefix']} not associated"


def _assert_footnotes(truth: dict[str, Any], layout: LayoutDocument) -> None:
    expected = truth.get("footnotesExpected", 0)
    footnotes = [region for region in layout.regions if region.kind == "FOOTNOTE"]
    assert len(footnotes) >= expected, (
        f"{truth['fixture']}: expected >= {expected} footnotes, found {len(footnotes)}"
    )
    for footnote in footnotes:
        assert footnote.id not in layout.primaryFlow
