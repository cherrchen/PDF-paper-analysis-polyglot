"""Phase 7.2 simulated specialist providers (deterministic ensemble baseline).

Two deterministic providers simulate the specialist roles the Capability
Registry (docs/architecture/document-architecture.md §35) assigns to real
parsers, without the heavy native dependencies:

- :class:`FakeDoclingTableProvider` (``docling-sim``) is the table.structure
  authority: it emits TABLE_STRUCTURE candidates with an explicit
  row/column/cell grid recovered from span geometry.
- :class:`FakeGrobidScholarlyProvider` (``grobid-sim``) is the scholarly
  metadata/bibliography authority: it emits METADATA and STRUCTURE
  candidates parsed from the first page and the reference section.

Both are evidence providers only — they never own the LayoutDocument or
SemanticDocument (parser-adapter-contract.md). Real MinerU / Docling /
GROBID adapters plug into the same EvidenceProvider Protocol later.
"""

from __future__ import annotations

import re

from document_model.generated import schema_models as generated

from pdf_pipeline.evidence.providers import CandidateSink
from pdf_pipeline.furniture import body_font_size, split_furniture
from pdf_pipeline.geometry import as_rect, containment
from pdf_pipeline.table_grid import (
    cluster_lines,
    column_centers,
    column_index,
    ordered_spans,
    table_grid_regions,
)

DOCLING_PROVIDER = "docling-sim"
DOCLING_PROVIDER_VERSION = "0.1.0"
GROBID_PROVIDER = "grobid-sim"
GROBID_PROVIDER_VERSION = "0.1.0"

# A span belongs to a table when at least this share of its area lies
# inside the detected table rect.
TABLE_CELL_CONTAINMENT = 0.7

# GROBID-sim text patterns.
_ABSTRACT_HEAD = re.compile(r"^abstract\b", re.IGNORECASE)
_REFERENCES_HEAD = re.compile(r"^(references|bibliography)\b", re.IGNORECASE)
_SECTION_HEAD = re.compile(r"^(\d+(?:\.\d+)*)\s+\S")
_AUTHOR_YEAR = re.compile(r"\([A-Z][A-Za-z'\-]+(?:\s+(?:et al\.?)?,?\s*\d{4}[a-z]?)\)")

# The docling-sim table grid is trusted more than the mock's table guess
# (authority role), but structured recovery is never certain.
TABLE_STRUCTURE_CONFIDENCE = 0.85
SCHOLARLY_METADATA_CONFIDENCE = 0.9
SCHOLARLY_STRUCTURE_CONFIDENCE = 0.8


class FakeDoclingTableProvider:
    """Table.structure authority: TABLE_STRUCTURE candidates from geometry."""

    name = DOCLING_PROVIDER
    version = DOCLING_PROVIDER_VERSION

    def __init__(self, fingerprint: str | None = None) -> None:
        self._explicit_fingerprint = fingerprint

    def collect(self, physical: generated.PhysicalDocument) -> generated.EvidenceBundle:
        fingerprint = self._explicit_fingerprint or physical.sourceFingerprint or physical.id
        sink = CandidateSink(fingerprint, self.name, self.version, f"{self.name}:")
        for page in physical.pages:
            spans = _page_text_spans(physical, page.id)
            body, _, _ = split_furniture(spans, page.geometry.heightPt, 0.0)
            for table_rect in table_grid_regions(body):
                _emit_table_structure(sink, page.id, table_rect, body)
        candidates, provenance = sink.finish()
        return generated.EvidenceBundle(
            schemaVersion="0.1.0",
            provider=self.name,
            providerVersion=self.version,
            candidates=candidates,
            provenance=provenance,
        )


class FakeGrobidScholarlyProvider:
    """Scholarly authority: METADATA + STRUCTURE candidates from text."""

    name = GROBID_PROVIDER
    version = GROBID_PROVIDER_VERSION

    def __init__(self, fingerprint: str | None = None) -> None:
        self._explicit_fingerprint = fingerprint

    def collect(self, physical: generated.PhysicalDocument) -> generated.EvidenceBundle:
        fingerprint = self._explicit_fingerprint or physical.sourceFingerprint or physical.id
        sink = CandidateSink(fingerprint, self.name, self.version, f"{self.name}:")
        _emit_scholarly(sink, physical)
        candidates, provenance = sink.finish()
        return generated.EvidenceBundle(
            schemaVersion="0.1.0",
            provider=self.name,
            providerVersion=self.version,
            candidates=candidates,
            provenance=provenance,
        )


def _page_text_spans(
    physical: generated.PhysicalDocument, page_id: str
) -> list[generated.TextSpan]:
    spans = [
        obj
        for obj in physical.objects
        if isinstance(obj, generated.TextSpan) and obj.pageId == page_id
    ]
    return ordered_spans(spans)


def _emit_table_structure(
    sink: CandidateSink,
    page_id: str,
    table_rect: generated.Rect,
    spans: list[generated.TextSpan],
) -> None:
    """Recover a deterministic cell grid inside one detected table rect."""
    members = [
        span
        for span in spans
        if containment(table_rect, as_rect(span.geometry)) >= TABLE_CELL_CONTAINMENT
    ]
    if len(members) < 2:
        return
    rows = cluster_lines(members)
    centers = column_centers(members)
    if not rows or not centers:
        return
    cells = [
        generated.TableCellCandidate(
            row=row_index,
            column=column_index(
                as_rect(span.geometry).x + as_rect(span.geometry).width / 2, centers
            ),
            rowSpan=1,
            colSpan=1,
            text=span.text.strip(),
        )
        for row_index, row in enumerate(rows)
        for span in row
    ]
    evidence_id = sink.derived_id(f"table-{rows[0][0].id}")
    candidate = generated.TableCandidate(
        evidenceType="TABLE_STRUCTURE",
        id=evidence_id,
        pageId=page_id,
        geometry=table_rect,
        rowCount=len(rows),
        columnCount=len(centers),
        cells=cells,
        confidence=TABLE_STRUCTURE_CONFIDENCE,
        provenanceIds=[],
    )
    sink.add_evidence(
        candidate,
        operation="table-structure",
        input_refs=[span.id for span in members],
    )


def _emit_scholarly(sink: CandidateSink, physical: generated.PhysicalDocument) -> None:
    """Parse title/author/abstract metadata and section structure roles."""
    first_page = physical.pages[0] if physical.pages else None
    if first_page is not None:
        spans = _page_text_spans(physical, first_page.id)
        body, _, _ = split_furniture(spans, first_page.geometry.heightPt, 0.0)
        body_font = body_font_size(body)
        fields: list[generated.MetadataField] = []
        if body:
            fields.append(generated.MetadataField(name="title", value=body[0].text.strip()))
        author_line = next(
            (span.text.strip() for span in body[1:4] if _looks_like_author_line(span, body_font)),
            None,
        )
        if author_line:
            fields.append(generated.MetadataField(name="author", value=author_line))
        abstract = _abstract_text(body)
        if abstract:
            fields.append(generated.MetadataField(name="abstract", value=abstract))
        if fields:
            sink.add_evidence(
                generated.MetadataCandidate(
                    evidenceType="METADATA",
                    id=_scholarly_id(sink, "metadata"),
                    fields=fields,
                    confidence=SCHOLARLY_METADATA_CONFIDENCE,
                    provenanceIds=[],
                ),
                operation="scholarly-metadata",
                input_refs=[span.id for span in body[:8]],
            )

    for page in physical.pages:
        spans = _page_text_spans(physical, page.id)
        body, _, _ = split_furniture(spans, page.geometry.heightPt, 0.0)
        for span in body:
            text = span.text.strip()
            role = _structure_role(text)
            if role is None:
                continue
            sink.add_evidence(
                generated.StructureCandidate(
                    evidenceType="STRUCTURE",
                    id=_scholarly_id(sink, f"structure-{span.id}"),
                    role=role,
                    textPreview=text[:200],
                    pageId=page.id,
                    geometry=as_rect(span.geometry),
                    confidence=SCHOLARLY_STRUCTURE_CONFIDENCE,
                    provenanceIds=[],
                ),
                operation="scholarly-structure",
                input_refs=[span.id],
            )


def _scholarly_id(sink: CandidateSink, local: str) -> str:
    return sink.derived_id(local)


def _looks_like_author_line(span: generated.TextSpan, body_font: float) -> bool:
    """Short author-style line under the title (names or affiliations)."""
    text = span.text.strip()
    if not text or len(text) > 120:
        return False
    if _ABSTRACT_HEAD.match(text) or _SECTION_HEAD.match(text):
        return False
    if body_font > 0 and _font_size(span) > body_font * 1.15:
        return False
    return "," in text or " and " in text or _AUTHOR_YEAR.search(text) is not None


def _abstract_text(body: list[generated.TextSpan]) -> str | None:
    """Join the span(s) that carry the abstract heading or its lead line."""
    for index, span in enumerate(body):
        if _ABSTRACT_HEAD.match(span.text.strip()):
            words = span.text.strip().split(None, 1)
            rest = words[1] if len(words) > 1 else ""
            parts = [rest] if rest else []
            for follower in body[index + 1 : index + 4]:
                if _SECTION_HEAD.match(follower.text.strip()):
                    break
                parts.append(follower.text.strip())
            text = " ".join(part for part in parts if part)
            return text[:600] or None
    return None


def _structure_role(text: str) -> generated.StructureRole | None:
    if _ABSTRACT_HEAD.match(text) and len(text) < 40:
        return "ABSTRACT"
    if _REFERENCES_HEAD.match(text) and len(text) < 40:
        return "REFERENCES"
    if _SECTION_HEAD.match(text) and len(text) <= 120:
        return "SECTION"
    return None


def _font_size(span: generated.TextSpan) -> float:
    if span.fontSize is not None and span.fontSize > 0:
        return span.fontSize
    return as_rect(span.geometry).height
