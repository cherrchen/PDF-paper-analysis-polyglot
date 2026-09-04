# pyright: reportUnknownMemberType=false
"""Phase 2.1 minimal PDF backend tests.

Covers the Roadmap M2 Phase 2.1 validation axes on first-party fixtures:
page count correctness, text completeness, and geometry sanity, plus the
determinism requirement ("same PDF bytes parsed twice belong to 2.1").
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pypdfium2 as pdfium
import pytest
from document_model.generated import schema_models as generated
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


def test_page_geometry_transforms_are_per_page_inverses() -> None:
    doc = extract_physical_document(_fixture_bytes("smoke"))
    geometry = doc.pages[0].geometry
    raw = geometry.rawToCanonical
    inverse = geometry.canonicalToRaw

    assert raw.f == geometry.heightPt
    assert inverse.f == geometry.heightPt
    raw_y = 123.5
    canonical_y = raw.b * 0.0 + raw.d * raw_y + raw.f
    roundtrip_y = inverse.b * 0.0 + inverse.d * canonical_y + inverse.f
    assert canonical_y == pytest.approx(geometry.heightPt - raw_y)
    assert roundtrip_y == pytest.approx(raw_y)


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_pdfium_rotation_transform_roundtrips(tmp_path: Path, rotation: int) -> None:
    path = tmp_path / f"rotated-{rotation}.pdf"
    pdf = pdfium.PdfDocument(_fixture_bytes("smoke"))
    page = pdf[0]
    unrotated_size = cast("tuple[float, float]", page.get_size())
    page.set_rotation(rotation)
    page.close()
    pdf.save(path)
    pdf.close()

    doc = extract_physical_document(path)
    geometry = doc.pages[0].geometry
    assert geometry.rotation == rotation
    expected_size = (
        (unrotated_size[1], unrotated_size[0]) if rotation in {90, 270} else unrotated_size
    )
    assert geometry.widthPt == pytest.approx(expected_size[0])
    assert geometry.heightPt == pytest.approx(expected_size[1])

    forward = geometry.rawToCanonical
    inverse = geometry.canonicalToRaw
    for raw_x, raw_y in ((0.0, 0.0), unrotated_size):
        canonical_x = forward.a * raw_x + forward.c * raw_y + forward.e
        canonical_y = forward.b * raw_x + forward.d * raw_y + forward.f
        roundtrip_x = inverse.a * canonical_x + inverse.c * canonical_y + inverse.e
        roundtrip_y = inverse.b * canonical_x + inverse.d * canonical_y + inverse.f
        assert 0 <= canonical_x <= geometry.widthPt
        assert 0 <= canonical_y <= geometry.heightPt
        assert roundtrip_x == pytest.approx(raw_x)
        assert roundtrip_y == pytest.approx(raw_y)
    for obj in doc.objects:
        assert isinstance(obj.geometry, generated.Rect)
        assert 0 <= obj.geometry.x <= geometry.widthPt
        assert 0 <= obj.geometry.y <= geometry.heightPt
        assert obj.geometry.x + obj.geometry.width <= geometry.widthPt + 0.01
        assert obj.geometry.y + obj.geometry.height <= geometry.heightPt + 0.01
