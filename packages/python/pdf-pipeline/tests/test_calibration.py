"""Phase 7.5/7.6 tests: confidence calibration and quality reporting.

Calibration buckets must separate high-confidence from low-confidence
correctness on synthetic samples; the quality report must aggregate the
roadmap Phase 7.6 metrics measurably on a real fixture (and report null
rather than invented values when truth is unavailable).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest
from pdf_pipeline.calibration import calibrate, calibration_samples
from pdf_pipeline.metrics import quality_report

FIXTURE_DIR = Path(__file__).resolve().parents[4] / "tests/fixtures/source/latex/build"


def test_calibrate_buckets_and_accuracy() -> None:
    samples = [(0.55, False), (0.58, False), (0.62, True), (0.85, True), (0.92, True)]
    report = calibrate(samples)
    assert report.total == 5
    assert report.correct == 3
    by_lower = {b.lower: b for b in report.bins}
    assert by_lower[0.5].total == 2
    assert by_lower[0.5].accuracy == 0.0
    assert by_lower[0.6].total == 1
    assert by_lower[0.6].accuracy == 1.0
    assert by_lower[0.9].accuracy == 1.0
    payload = report.to_json()
    json.dumps(payload)  # report must be JSON-able
    assert payload["monotonic"] is True


def test_calibrate_detects_non_monotonic_confidence() -> None:
    samples = [(0.55, True), (0.62, False), (0.72, False), (0.82, False)]
    report = calibrate(samples)
    assert report.monotonic is False


def test_calibration_samples_pair_confidence_with_truth() -> None:
    pytest.importorskip("pdf_pipeline.layout")
    from document_model import dump_document
    from pdf_pipeline.evidence.providers import MockLayoutEvidenceProvider
    from pdf_pipeline.layout import recover_layout_document
    from pdf_pipeline.physical import extract_physical_document
    from pdf_pipeline.pipeline import region_texts_from

    fixture = FIXTURE_DIR / "smoke.pdf"
    if not fixture.exists():
        pytest.skip("smoke fixture PDF not built; run `just latex-smoke`")
    physical = extract_physical_document(fixture.read_bytes())
    evidence = MockLayoutEvidenceProvider().collect(physical)
    layout = recover_layout_document(physical, evidence=evidence)
    texts = region_texts_from(physical, layout)
    truth = json.loads(
        (Path(__file__).resolve().parents[4] / "tests/fixtures/layout-truth/smoke.json").read_text()
    )
    samples = calibration_samples(layout, texts, truth["readingOrder"], truth.get("regions"))
    assert samples
    assert all(0.0 <= confidence <= 1.0 for confidence, _ in samples)
    dump_document(layout)


def test_quality_report_on_fixture() -> None:
    pytest.importorskip("pdf_pipeline.semantic")
    from pdf_pipeline.evidence.providers import MockLayoutEvidenceProvider
    from pdf_pipeline.layout import recover_layout_document
    from pdf_pipeline.physical import extract_physical_document
    from pdf_pipeline.pipeline import region_lines_from, region_texts_from
    from pdf_pipeline.semantic import recover_semantic_document

    fixture = FIXTURE_DIR / "smoke.pdf"
    if not fixture.exists():
        pytest.skip("smoke fixture PDF not built; run `just latex-smoke`")
    physical = extract_physical_document(fixture.read_bytes())
    evidence = MockLayoutEvidenceProvider().collect(physical)
    layout = recover_layout_document(physical, evidence=evidence)
    texts = region_texts_from(physical, layout)
    semantic = recover_semantic_document(layout, texts, lines=region_lines_from(physical, layout))
    report = quality_report(physical=physical, layout=layout, semantic=semantic, region_texts=texts)
    json.dumps(report)
    coverage = cast("float", report["physicalTextCoverage"])
    source_coverage = cast("float", report["sourceMappingCoverage"])
    citation_rate = cast("float", report["citationResolutionRate"])
    assert coverage > 0.9
    assert source_coverage == 1.0
    assert citation_rate == 1.0
    # Without hand truth, truth-dependent metrics stay null, not invented.
    assert report["semanticExpectationCoverage"] is None
    assert report["paragraphLabelRecall"] is None
    assert report["headingLabelRecall"] is None
    assert "paragraphRecoveryAccuracy" not in report
    assert "sectionHierarchyAccuracy" not in report
    assert "byCategory" in cast("dict[str, object]", report["issues"])
    assert "bySeverity" in cast("dict[str, object]", report["issues"])
