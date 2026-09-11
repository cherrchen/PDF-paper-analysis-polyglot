"""Phase 7.2 Capability Registry + simulated specialist provider tests.

FakeDoclingTableProvider / FakeGrobidScholarlyProvider must emit schema-
valid, deterministic evidence bundles that respect their registry roles,
and the registry must keep internal capabilities internal-owned.
"""

from __future__ import annotations

from document_model import dump_document, load_document
from document_model.generated import schema_models as generated
from pdf_pipeline.capabilities import authority_rank, is_authority, load_registry
from pdf_pipeline.evidence.fake_specialists import (
    FakeDoclingTableProvider,
    FakeGrobidScholarlyProvider,
)

COUNTER = iter(range(30000, 40000))


def _uid() -> str:
    return f"00000000-0000-0000-0000-{next(COUNTER):012d}"


def _span(x: float, y: float, width: float, height: float, text: str) -> generated.TextSpan:
    return generated.TextSpan(
        objectType="textSpan",
        id=_uid(),
        pageId=_uid(),
        text=text,
        geometry=generated.Rect(kind="rect", x=x, y=y, width=width, height=height),
        font=generated.FontRef(name=""),
        fontSize=height,
    )


def _physical(
    pages: list[list[generated.TextSpan]],
    width: float = 600.0,
    height: float = 800.0,
) -> generated.PhysicalDocument:
    result_pages: list[generated.PhysicalPage] = []
    objects: list[generated.PhysicalObject] = []
    for index, spans in enumerate(pages):
        page_id = _uid()
        for span in spans:
            span.pageId = page_id
        objects.extend(spans)
        result_pages.append(
            generated.PhysicalPage(
                id=page_id,
                index=index,
                geometry=generated.PageGeometry(
                    widthPt=width,
                    heightPt=height,
                    rotation=0,
                    rawToCanonical=generated.Matrix(a=1, b=0, c=0, d=1, e=0, f=0),
                    canonicalToRaw=generated.Matrix(a=1, b=0, c=0, d=1, e=0, f=0),
                ),
                objectIds=[span.id for span in spans],
            )
        )
    return generated.PhysicalDocument(
        schemaVersion="0.1.0",
        id=_uid(),
        pages=result_pages,
        objects=objects,
        metadata=generated.PhysicalMetadata(),
    )


# --- Capability registry -------------------------------------------------


def test_registry_keeps_semantic_ownership_internal() -> None:
    registry = load_registry()
    assert registry["semantic.document"].primary == "internal"
    assert registry["layout.reading_order"].primary == "internal"


def test_registry_assigns_specialist_authorities() -> None:
    registry = load_registry()
    assert registry["table.structure"].primary == "docling-sim"
    assert registry["scholarly.bibliography"].primary == "grobid-sim"
    assert registry["layout.region"].primary == "mock"


def test_authority_rank_orders_providers() -> None:
    registry = load_registry()
    capability = registry["table.structure"]
    ranks = [authority_rank(registry, "table.structure", p) for p in capability.authorities()]
    assert ranks == sorted(ranks)
    unlisted = authority_rank(registry, "table.structure", "unknown-provider")
    assert unlisted > ranks[-1]
    assert is_authority(registry, "table.structure", "docling-sim")
    assert not is_authority(registry, "table.structure", "unknown-provider")


# --- FakeDoclingTableProvider --------------------------------------------


def _table_page() -> generated.PhysicalDocument:
    """A 3x2 numeric table plus body prose above it."""
    page: list[generated.TextSpan] = [
        _span(70, 60, 460, 10, "Body prose before the table."),
    ]
    for row_index, y in enumerate((120.0, 140.0, 160.0)):
        page.append(_span(70, y, 100, 10, f"row{row_index}a 1.0"))
        page.append(_span(200, y, 100, 10, f"row{row_index}b 2.0"))
    return _physical([page])


def test_docling_sim_emits_structured_table() -> None:
    physical = _table_page()
    bundle = FakeDoclingTableProvider().collect(physical)
    tables = [
        candidate for candidate in bundle.candidates if candidate.evidenceType == "TABLE_STRUCTURE"
    ]
    assert len(tables) == 1
    table = tables[0]
    assert table.rowCount == 3
    assert table.columnCount == 2
    assert {cell.row for cell in table.cells} == {0, 1, 2}
    assert {cell.column for cell in table.cells} == {0, 1}
    assert table.confidence == 0.85
    dump_document(bundle)
    load_document("evidence", dump_document(bundle))


def test_docling_sim_is_deterministic_and_namespaces_ids() -> None:
    physical = _table_page()
    provider = FakeDoclingTableProvider()
    first = provider.collect(physical)
    second = provider.collect(physical)
    assert dump_document(first) == dump_document(second)
    mock_bundle = (
        __import__("pdf_pipeline.evidence.providers", fromlist=["MockLayoutEvidenceProvider"])
        .MockLayoutEvidenceProvider()
        .collect(physical)
    )
    docling_ids = {candidate.id for candidate in first.candidates}
    mock_ids = {candidate.id for candidate in mock_bundle.candidates}
    assert docling_ids.isdisjoint(mock_ids)


def test_docling_sim_emits_nothing_without_tables() -> None:
    physical = _physical([[_span(70, 60, 460, 10, "Plain prose page. No table.")]])
    bundle = FakeDoclingTableProvider().collect(physical)
    assert all(candidate.evidenceType != "TABLE_STRUCTURE" for candidate in bundle.candidates)


# --- FakeGrobidScholarlyProvider -----------------------------------------


def _scholarly_page() -> generated.PhysicalDocument:
    page = [
        _span(100, 40, 400, 14, "Attention Is All You Need"),
        _span(120, 70, 360, 10, "Vaswani, Shazeer and Parmar"),
        _span(70, 100, 460, 10, "Abstract"),
        _span(70, 120, 460, 10, "We propose a new architecture for sequence transduction."),
        _span(70, 150, 460, 10, "1 Introduction"),
        _span(70, 170, 460, 10, "Recurrent models dominate sequence modeling today."),
        _span(70, 200, 460, 10, "References"),
    ]
    return _physical([page])


def test_grobid_sim_emits_metadata_and_structure() -> None:
    physical = _scholarly_page()
    bundle = FakeGrobidScholarlyProvider().collect(physical)
    metadata = [c for c in bundle.candidates if c.evidenceType == "METADATA"]
    structure = [c for c in bundle.candidates if c.evidenceType == "STRUCTURE"]
    assert len(metadata) == 1
    fields = {field.name: field.value for field in metadata[0].fields}
    assert fields["title"] == "Attention Is All You Need"
    assert fields["author"] == "Vaswani, Shazeer and Parmar"
    assert fields["abstract"].startswith("We propose")
    roles = {candidate.role for candidate in structure}
    assert "ABSTRACT" in roles
    assert "REFERENCES" in roles
    assert "SECTION" in roles
    dump_document(bundle)
    load_document("evidence", dump_document(bundle))


def test_grobid_sim_is_deterministic() -> None:
    physical = _scholarly_page()
    provider = FakeGrobidScholarlyProvider()
    assert dump_document(provider.collect(physical)) == dump_document(provider.collect(physical))


def test_grobid_sim_skips_plain_pages() -> None:
    physical = _physical([[_span(70, 60, 460, 10, "Just a plain body paragraph with content.")]])
    bundle = FakeGrobidScholarlyProvider().collect(physical)
    assert bundle.candidates  # title metadata is still derived
    assert all(candidate.evidenceType == "METADATA" for candidate in bundle.candidates)
