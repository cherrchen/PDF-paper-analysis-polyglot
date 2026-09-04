"""Phase 2.1 minimal PDF backend tests.

Covers the Roadmap M2 Phase 2.1 validation axes on first-party fixtures:
page count correctness, text completeness, and geometry sanity, plus the
determinism requirement ("same PDF bytes parsed twice belong to 2.1").
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pdf_pipeline.physical import (
    extract_physical_document,
    source_fingerprint,
    write_physical_document,
)

FIXTURE_DIR = Path(__file__).resolve().parents[4] / "tests/fixtures/source/latex/build"

FIXTURES: dict[str, dict[str, object]] = {
    "smoke": {"pages": 1, "expect_text": "Smoke Fixture"},
    "two-column": {"pages": 1, "expect_text": "Two-Column Fixture"},
    "spanning-figure": {"pages": 2, "expect_text": None},
}


def _fixture_bytes(name: str) -> bytes:
    path = FIXTURE_DIR / f"{name}.pdf"
    if not path.exists():
        pytest.skip(f"fixture PDF {name} not built; run `just latex-smoke`")
    return path.read_bytes()


@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_page_count_correct(name: str) -> None:
    doc = extract_physical_document(_fixture_bytes(name))
    assert len(doc.pages) == FIXTURES[name]["pages"]
    assert doc.metadata.pageCount == len(doc.pages)


@pytest.mark.parametrize("name", ["smoke", "two-column"])
def test_text_basic_complete(name: str) -> None:
    doc = extract_physical_document(_fixture_bytes(name))
    text = " ".join(o.text for o in doc.objects if o.objectType == "textSpan")
    expected = FIXTURES[name]["expect_text"]
    assert isinstance(expected, str)
    assert expected in text
    assert len(text) > 50


@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_geometry_within_canonical_page(name: str) -> None:
    doc = extract_physical_document(_fixture_bytes(name))
    page_by_id = {page.id: page for page in doc.pages}
    for obj in doc.objects:
        page = page_by_id[obj.pageId]
        rect = obj.geometry
        assert rect.kind == "rect"
        assert 0 <= rect.x <= page.geometry.widthPt
        assert 0 <= rect.y <= page.geometry.heightPt
        assert rect.width >= 0
        assert rect.height >= 0


def test_same_bytes_parse_deterministically() -> None:
    data = _fixture_bytes("smoke")
    first = extract_physical_document(data)
    second = extract_physical_document(data)
    assert first == second
    assert first.sourceFingerprint == source_fingerprint(data)


def test_serialization_roundtrip(tmp_path: Path) -> None:
    doc = extract_physical_document(_fixture_bytes("smoke"))
    data = write_physical_document(doc, tmp_path / "physical.json")
    assert data["schemaVersion"] == "0.1.0"
    assert (tmp_path / "physical.json").exists()
