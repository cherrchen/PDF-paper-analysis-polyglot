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


def test_mineru_formula_ids_include_page() -> None:
    physical = _physical(page_count=2)
    bundle = MinerUEvidenceProvider(dump_path=DUMP_ROOT / "mineru/two-page-formulas.json").collect(
        physical
    )
    load_document("evidence", dump_document(bundle))
    formulas = [c for c in bundle.candidates if c.evidenceType == "FORMULA"]
    assert len(formulas) == 2
    assert formulas[0].id != formulas[1].id
    assert formulas[0].pageId != formulas[1].pageId
    assert {c.latex for c in formulas} == {"E = mc^{2}", "a^2 + b^2 = c^2"}


def test_docling_dump_maps_table_structure() -> None:
    physical = _physical()
    bundle = DoclingEvidenceProvider(dump_path=DUMP_ROOT / "docling/table.json").collect(physical)
    load_document("evidence", dump_document(bundle))
    tables = [c for c in bundle.candidates if c.evidenceType == "TABLE_STRUCTURE"]
    assert len(tables) == 1
    assert tables[0].rowCount == 2
    assert tables[0].columnCount == 2
    assert tables[0].cells[0].text == "H1"


def test_docling_native_origin_and_merged_cells() -> None:
    from pdf_pipeline.evidence.normalize import normalize_bundle

    physical = _physical()
    bundle = DoclingEvidenceProvider(dump_path=DUMP_ROOT / "docling/native-v2.48.json").collect(
        physical
    )
    load_document("evidence", dump_document(bundle))
    regions = {
        candidate.textPreview: candidate
        for candidate in bundle.candidates
        if isinstance(candidate, generated.RegionCandidate)
    }
    bottom_left = regions["Bottom-left origin paragraph."]
    top_left = regions["Top-left origin heading."]
    assert isinstance(bottom_left.geometry, generated.Rect)
    assert isinstance(top_left.geometry, generated.Rect)
    assert bottom_left.geometry.height == 40
    assert bottom_left.geometry.y == pytest.approx(100)
    assert top_left.geometry.height == 30
    assert top_left.geometry.y == pytest.approx(80)
    normalized = normalize_bundle(bundle, physical)
    previews = {item.textPreview for item in normalized}
    assert "Bottom-left origin paragraph." in previews

    tables = [c for c in bundle.candidates if c.evidenceType == "TABLE_STRUCTURE"]
    assert len(tables) == 2
    merged, grid_only = tables
    assert merged.rowCount == 2
    assert merged.columnCount == 2
    assert [(cell.row, cell.column, cell.colSpan, cell.text) for cell in merged.cells] == [
        (0, 0, 2, "Merged header"),
        (1, 0, 1, "a"),
        (1, 1, 1, "b"),
    ]
    assert [(cell.row, cell.column, cell.colSpan, cell.text) for cell in grid_only.cells] == [
        (0, 0, 2, "Grid-only span")
    ]
    assert all(cell.column + cell.colSpan <= merged.columnCount for cell in merged.cells)
    assert all(cell.column + cell.colSpan <= grid_only.columnCount for cell in grid_only.cells)


def test_parse_rect_converts_docling_origins() -> None:
    from pdf_pipeline.evidence.native import parse_rect

    top_left = parse_rect({"l": 72, "t": 80, "r": 400, "b": 110, "coord_origin": "TOPLEFT"})
    assert (top_left.y, top_left.height) == (80, 30)
    bottom_left = parse_rect(
        {"l": 72, "t": 692, "r": 500, "b": 652, "coord_origin": "BOTTOMLEFT"},
        page_height=792,
    )
    assert bottom_left.y == pytest.approx(100)
    assert bottom_left.height == pytest.approx(40)
    with pytest.raises(ValueError, match="page_height"):
        parse_rect({"l": 72, "t": 692, "r": 500, "b": 652, "coord_origin": "BOTTOMLEFT"})


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


def test_grobid_live_posts_multipart_input(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from threading import Thread

    from pdf_pipeline.evidence.grobid import GROBID_URL_ENV
    from pdf_pipeline.evidence.native import SOURCE_PDF_ENV

    captured: dict[str, object] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            captured["path"] = self.path
            captured["content_type"] = self.headers.get("Content-Type")
            captured["body"] = self.rfile.read(length)
            self.send_response(200)
            self.send_header("Content-Type", "application/xml")
            self.end_headers()
            self.wfile.write(
                b'<?xml version="1.0"?><TEI xmlns="http://www.tei-c.org/ns/1.0">'
                b"<teiHeader><fileDesc><titleStmt><title>Live Title</title>"
                b"</titleStmt></fileDesc></teiHeader></TEI>"
            )

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            del format, args

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.4 live-stub")
    monkeypatch.setenv(GROBID_URL_ENV, f"http://127.0.0.1:{server.server_address[1]}")
    monkeypatch.setenv(SOURCE_PDF_ENV, str(pdf))
    try:
        bundle = GrobidEvidenceProvider().collect(_physical())
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    load_document("evidence", dump_document(bundle))
    assert captured["path"] == "/api/processFulltextDocument"
    content_type = str(captured["content_type"])
    assert content_type.startswith("multipart/form-data")
    assert "boundary=" in content_type
    body = captured["body"]
    assert isinstance(body, bytes)
    assert b'name="input"' in body
    assert b'filename="paper.pdf"' in body
    assert b"Content-Type: application/pdf" in body
    assert b"%PDF-1.4 live-stub" in body
    fields = {
        field.name: field.value
        for candidate in bundle.candidates
        if isinstance(candidate, generated.MetadataCandidate)
        for field in candidate.fields
    }
    assert fields["title"] == "Live Title"
