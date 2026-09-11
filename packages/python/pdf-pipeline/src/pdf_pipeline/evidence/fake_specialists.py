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

DOCLING_PROVIDER = "docling-sim"
DOCLING_PROVIDER_VERSION = "0.1.0"
GROBID_PROVIDER = "grobid-sim"
GROBID_PROVIDER_VERSION = "0.1.0"

# A span belongs to a table when at least this share of its area lies
# inside the detected table rect.
TABLE_CELL_CONTAINMENT = 0.7

# A grid needs at least this many consecutive aligned multi-span rows.
TABLE_MIN_GRID_ROWS = 2
TABLE_MIN_GRID_COLUMNS = 2

# Row/column clustering tolerances (PDF points).
CELL_ROW_GAP_FACTOR = 0.6
CELL_LINE_GAP_FACTOR = 0.4
CELL_COLUMN_TOLERANCE_PT = 5.0

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
            for table_rect in _table_grid_regions(body):
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
    return _ordered(spans)


def _ordered(spans: list[generated.TextSpan]) -> list[generated.TextSpan]:
    return sorted(spans, key=lambda span: (as_rect(span.geometry).y, as_rect(span.geometry).x))


def _table_grid_regions(
    spans: list[generated.TextSpan],
) -> list[generated.Rect]:
    """Detect grid-like table regions from span geometry.

    A table is a maximal run of consecutive multi-span lines whose column
    count matches and whose column x-centers stay aligned within
    tolerance — a deterministic baseline for what Docling recovers from
    ruling lines in real PDFs.
    """
    lines = _cluster_lines(spans)
    grids: list[list[list[generated.TextSpan]]] = []
    current: list[list[generated.TextSpan]] = []
    current_centers: list[list[float]] = []
    for line in lines:
        if len(line) < TABLE_MIN_GRID_COLUMNS:
            current = []
            current_centers = []
            continue
        centers = _column_centers(line)
        if current and not _columns_aligned(centers, current_centers[-1]):
            if len(current) >= TABLE_MIN_GRID_ROWS:
                grids.append(current)
            current = []
            current_centers = []
        current.append(line)
        current_centers.append(centers)
    if len(current) >= TABLE_MIN_GRID_ROWS:
        grids.append(current)
    return [_union_rect(lines_) for lines_ in grids]


def _columns_aligned(a: list[float], b: list[float]) -> bool:
    return len(a) == len(b) and all(
        abs(x - y) <= CELL_COLUMN_TOLERANCE_PT for x, y in zip(a, b, strict=True)
    )


def _cluster_lines(spans: list[generated.TextSpan]) -> list[list[generated.TextSpan]]:
    """Group spans into visual lines by shared y-band."""
    lines: list[list[generated.TextSpan]] = []
    for span in _ordered(spans):
        rect = as_rect(span.geometry)
        if lines:
            last_rect = as_rect(lines[-1][-1].geometry)
            line_gap = CELL_LINE_GAP_FACTOR * max(rect.height, last_rect.height)
            same_line = abs(rect.y - last_rect.y) <= line_gap or (
                rect.y < last_rect.y + last_rect.height and last_rect.y < rect.y + rect.height
            )
            if same_line:
                lines[-1].append(span)
                continue
        lines.append([span])
    return lines


def _union_rect(lines: list[list[generated.TextSpan]]) -> generated.Rect:
    rect = as_rect(lines[0][0].geometry)
    for line in lines:
        for span in line:
            other = as_rect(span.geometry)
            rect = generated.Rect(
                kind="rect",
                x=min(rect.x, other.x),
                y=min(rect.y, other.y),
                width=max(rect.x + rect.width, other.x + other.width) - min(rect.x, other.x),
                height=max(rect.y + rect.height, other.y + other.height) - min(rect.y, other.y),
            )
    return rect


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
    rows = _cluster_rows(members)
    column_centers = _column_centers(members)
    if not rows or not column_centers:
        return
    cells = [
        generated.TableCellCandidate(
            row=row_index,
            column=_column_index(as_rect(span.geometry).x, column_centers),
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
        columnCount=len(column_centers),
        cells=cells,
        confidence=TABLE_STRUCTURE_CONFIDENCE,
        provenanceIds=[],
    )
    sink.add_evidence(
        candidate,
        operation="table-structure",
        input_refs=[span.id for span in members],
    )


def _cluster_rows(spans: list[generated.TextSpan]) -> list[list[generated.TextSpan]]:
    """Group table spans into rows by vertical position."""
    ordered = _ordered(spans)
    rows: list[list[generated.TextSpan]] = []
    for span in ordered:
        rect = as_rect(span.geometry)
        if rows:
            last = rows[-1][-1]
            last_rect = as_rect(last.geometry)
            gap = rect.y - (last_rect.y + last_rect.height)
            if gap <= CELL_ROW_GAP_FACTOR * max(rect.height, last_rect.height, 1.0):
                rows[-1].append(span)
                continue
        rows.append([span])
    return rows


def _column_centers(spans: list[generated.TextSpan]) -> list[float]:
    """Cluster span left edges into column centers."""
    centers: list[float] = []
    for span in sorted(spans, key=lambda s: as_rect(s.geometry).x):
        x = as_rect(span.geometry).x
        if centers and abs(x - centers[-1]) <= CELL_COLUMN_TOLERANCE_PT:
            continue
        centers.append(x)
    return centers


def _column_index(x: float, centers: list[float]) -> int:
    return min(range(len(centers)), key=lambda i: abs(x - centers[i]))


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
