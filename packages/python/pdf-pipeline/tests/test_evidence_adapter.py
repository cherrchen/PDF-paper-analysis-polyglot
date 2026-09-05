"""Phase 3.1 evidence tests: providers, normalization, adapter boundary."""

from __future__ import annotations

from pathlib import Path

import pytest
from document_model import dump_document, load_document
from pdf_pipeline.evidence import (
    MockLayoutEvidenceProvider,
    normalize_bundle,
    normalize_geometry,
    normalize_label,
)
from pdf_pipeline.geometry import as_rect
from pdf_pipeline.physical import extract_physical_document

FIXTURE_DIR = Path(__file__).resolve().parents[4] / "tests/fixtures/source/latex/build"


def _fixture(name: str) -> bytes:
    path = FIXTURE_DIR / f"{name}.pdf"
    if not path.exists():
        pytest.skip(f"fixture PDF {name} not available")
    return path.read_bytes()


def test_mock_provider_bundle_is_valid_and_deterministic() -> None:
    physical = extract_physical_document(_fixture("smoke"))
    bundle = MockLayoutEvidenceProvider().collect(physical)
    data = dump_document(bundle)
    load_document("evidence", data)
    again = MockLayoutEvidenceProvider().collect(extract_physical_document(_fixture("smoke")))
    assert dump_document(again) == data


def test_provider_never_sees_or_emits_document_model() -> None:
    physical = extract_physical_document(_fixture("smoke"))
    bundle = MockLayoutEvidenceProvider().collect(physical)
    assert bundle.provider == "mock"
    for candidate in bundle.candidates:
        # Candidates carry normalized labels + providerLabel only: no
        # LayoutRegion / SemanticNode types leak in either direction.
        assert candidate.evidenceType in {"REGION", "TABLE_STRUCTURE", "FORMULA"}
        assert isinstance(candidate.provenanceIds, list)


def test_normalize_label_maps_native_and_canonical_labels() -> None:
    assert normalize_label("para") == "PARAGRAPH_LIKE"
    assert normalize_label("title") == "HEADING_LIKE"
    assert normalize_label("display_formula") == "FORMULA"
    # Idempotent on canonical labels.
    assert normalize_label("PARAGRAPH_LIKE") == "PARAGRAPH_LIKE"
    assert normalize_label("HEADER") == "HEADER"
    # Unknown labels degrade, never crash.
    assert normalize_label("mystery-box") == "UNKNOWN"


def test_normalize_geometry_applies_provider_space() -> None:
    from document_model.generated import schema_models as generated

    page = generated.PhysicalPage(
        id="00000000-0000-0000-0000-00000000000f",
        index=0,
        geometry=generated.PageGeometry(
            widthPt=100,
            heightPt=200,
            rotation=0,
            rawToCanonical=generated.Matrix(a=1, b=0, c=0, d=1, e=0, f=0),
            canonicalToRaw=generated.Matrix(a=1, b=0, c=0, d=1, e=0, f=0),
        ),
        objectIds=[],
    )
    rect = generated.Rect(kind="rect", x=5, y=10, width=20, height=30)
    assert normalize_geometry(rect, page) is rect or normalize_geometry(rect, page) == rect

    shifted = generated.Matrix(a=1, b=0, c=0, d=1, e=10, f=20)
    moved = normalize_geometry(rect, page, provider_space=shifted)
    assert (moved.x, moved.y) == (15, 30)


def test_normalize_bundle_normalizes_candidates() -> None:
    physical = extract_physical_document(_fixture("figure-caption"))
    bundle = MockLayoutEvidenceProvider().collect(physical)
    candidates = normalize_bundle(bundle, physical)
    assert candidates, "figure-caption fixture must yield candidates"
    for candidate in candidates:
        assert candidate.label != "UNKNOWN" or candidate.providerLabel == "abandon"
        assert candidate.rect.width > 0
        assert candidate.rect.height > 0
        assert candidate.provider == "mock"
        assert as_rect(candidate.rect).width == candidate.rect.width


def test_caption_and_table_candidates_on_fixtures() -> None:
    physical = extract_physical_document(_fixture("table-heavy"))
    bundle = MockLayoutEvidenceProvider().collect(physical)
    labels = {
        candidate.normalizedLabel
        for candidate in bundle.candidates
        if candidate.evidenceType == "REGION"
    }
    assert "TABLE" in labels
    captions = [
        candidate
        for candidate in bundle.candidates
        if getattr(candidate, "normalizedLabel", None) == "CAPTION_LIKE"
    ]
    assert captions, "table caption should be a caption candidate"
