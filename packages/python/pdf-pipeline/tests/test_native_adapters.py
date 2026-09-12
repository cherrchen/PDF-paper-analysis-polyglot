"""Native MinerU / Docling / GROBID dump adapters map to EvidenceBundle only."""

from __future__ import annotations

from pathlib import Path

import pytest
from document_model import dump_document, load_document
from document_model.generated import schema_models as generated
from pdf_pipeline.evidence.docling import DoclingEvidenceProvider
from pdf_pipeline.evidence.grobid import GrobidEvidenceProvider
from pdf_pipeline.evidence.mineru import MinerUEvidenceProvider
from pdf_pipeline.routing import build_provider

DUMP_ROOT = Path(__file__).resolve().parents[4] / "tests/fixtures/parser-dumps"
COUNTER = iter(range(50000, 60000))


def _uid() -> str:
    return f"00000000-0000-0000-0000-{next(COUNTER):012d}"


def _physical(page_count: int = 1) -> generated.PhysicalDocument:
    pages = [
        generated.PhysicalPage(
            id=_uid(),
            index=index,
            geometry=generated.PageGeometry(
                widthPt=612,
                heightPt=792,
                rotation=0,
                rawToCanonical=generated.Matrix(a=1, b=0, c=0, d=1, e=0, f=0),
                canonicalToRaw=generated.Matrix(a=1, b=0, c=0, d=1, e=0, f=0),
            ),
            objectIds=[],
        )
        for index in range(page_count)
    ]
    return generated.PhysicalDocument(
        schemaVersion="0.1.0",
        id=_uid(),
        sourceFingerprint="dump-fixture",
        pages=pages,
        objects=[],
        metadata=generated.PhysicalMetadata(),
    )


def test_mineru_dump_maps_layout_and_formula() -> None:
    physical = _physical()
    bundle = MinerUEvidenceProvider(dump_path=DUMP_ROOT / "mineru/layout.json").collect(physical)
    load_document("evidence", dump_document(bundle))
    assert bundle.provider == "mineru"
    labels = {
        candidate.providerLabel: candidate.normalizedLabel
        for candidate in bundle.candidates
        if isinstance(candidate, generated.RegionCandidate)
    }
    assert labels["title"] == "HEADING_LIKE"
    assert labels["plain text"] == "PARAGRAPH_LIKE"
    assert labels["image"] == "FIGURE"
    formulas = [c for c in bundle.candidates if c.evidenceType == "FORMULA"]
    assert formulas[0].latex == "E = mc^{2}"


def test_docling_dump_maps_table_structure() -> None:
    physical = _physical()
    bundle = DoclingEvidenceProvider(dump_path=DUMP_ROOT / "docling/table.json").collect(physical)
    load_document("evidence", dump_document(bundle))
    tables = [c for c in bundle.candidates if c.evidenceType == "TABLE_STRUCTURE"]
    assert len(tables) == 1
    assert tables[0].rowCount == 2
    assert tables[0].columnCount == 2
    assert tables[0].cells[0].text == "H1"


def test_grobid_json_and_tei_dumps_map_metadata() -> None:
    physical = _physical()
    json_bundle = GrobidEvidenceProvider(dump_path=DUMP_ROOT / "grobid/header.json").collect(
        physical
    )
    tei_bundle = GrobidEvidenceProvider(dump_path=DUMP_ROOT / "grobid/header.tei.xml").collect(
        physical
    )
    load_document("evidence", dump_document(json_bundle))
    load_document("evidence", dump_document(tei_bundle))
    json_fields = {
        field.name: field.value
        for candidate in json_bundle.candidates
        if isinstance(candidate, generated.MetadataCandidate)
        for field in candidate.fields
    }
    assert json_fields["title"] == "Dump Paper Title"
    roles = {
        candidate.role
        for candidate in tei_bundle.candidates
        if isinstance(candidate, generated.StructureCandidate)
    }
    assert "ABSTRACT" in roles
    assert "REFERENCES" in roles


def test_native_bundle_forbids_provider_keys() -> None:
    physical = _physical()
    bundles = [
        dump_document(
            MinerUEvidenceProvider(dump_path=DUMP_ROOT / "mineru/layout.json").collect(physical)
        ),
        dump_document(
            DoclingEvidenceProvider(dump_path=DUMP_ROOT / "docling/table.json").collect(physical)
        ),
        dump_document(
            GrobidEvidenceProvider(dump_path=DUMP_ROOT / "grobid/header.json").collect(physical)
        ),
    ]
    leaked = {"pdf_info", "para_blocks", "texts", "tables", "teiHeader", "middle"}
    for dumped in bundles:
        assert leaked.isdisjoint(dumped)


def test_build_provider_registers_real_adapter_names() -> None:
    assert build_provider("mineru").name == "mineru"
    assert build_provider("docling").name == "docling"
    assert build_provider("grobid").name == "grobid"


def test_real_adapter_without_dump_fails_loudly() -> None:
    physical = _physical()
    with pytest.raises(FileNotFoundError, match="MINERU_DUMP"):
        MinerUEvidenceProvider().collect(physical)
