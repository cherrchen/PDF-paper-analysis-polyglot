"""Phase 3.1 evidence providers: adapter boundary for third-party parsers.

An :class:`EvidenceProvider` translates parser-specific output into a
canonical :class:`~document_model.generated.EvidenceBundle`. Providers are
the only place where parser schemas are touched; recovery engines consume
normalized candidates exclusively (docs/contracts/parser-adapter-contract.md).

``MockLayoutEvidenceProvider`` is the deterministic M3 baseline provider. It
simulates a layout-specialist parser (MinerU-like capabilities) on top of
the PhysicalDocument so Region Fusion can be developed and benchmarked
without the heavy MinerU dependency; a real MinerU adapter plugs into the
same Protocol later (heavy native dependencies require an Agent Note).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Protocol

from document_model import stable_uuid
from document_model.generated import schema_models as generated

from pdf_pipeline.furniture import body_font_size, split_furniture
from pdf_pipeline.geometry import as_rect, overlap_ratio, union_rect, vertical_gap

if TYPE_CHECKING:
    from collections.abc import Iterable

MOCK_PROVIDER = "mock"
MOCK_PROVIDER_VERSION = "0.1.0"

# Line clustering into paragraph candidates.
PARA_MAX_GAP_FACTOR = 0.9
PARA_MIN_X_OVERLAP = 0.5

# Caption prefix pattern ("Figure 1", "Fig. 2", "Table 3").
_CAPTION_PREFIX = re.compile(r"^(Figure|Fig\.?|Table)\s+\d+", re.IGNORECASE)

# Math-symbol density for formula candidates.
_FORMULA_CHARS = set("=+−×÷∑∫∏√∞≠≤≥±()[]{}^_\\αβγδϵθλμπσφω")  # noqa: RUF001


class EvidenceProvider(Protocol):
    """Adapter boundary: parser output -> canonical EvidenceBundle."""

    name: str
    version: str

    def collect(self, physical: generated.PhysicalDocument) -> generated.EvidenceBundle:
        """Produce the unified evidence bundle for a document."""
        ...


class _CandidateSink:
    """Accumulates candidates and their per-candidate provenance records."""

    def __init__(self, fingerprint: str) -> None:
        self._fingerprint = fingerprint
        self._candidates: list[generated.Evidence] = []
        self._records: list[generated.ProvenanceRecord] = []
        self._counter = 0

    def add_region(
        self,
        *,
        page_id: str,
        rect: generated.Rect,
        normalized_label: generated.LayoutLabel,
        provider_label: str,
        confidence: float,
        text_preview: str = "",
        input_refs: Iterable[str] = (),
    ) -> None:
        self._counter += 1
        evidence_id = stable_uuid(self._fingerprint, "evidence", self._counter)
        record_id = stable_uuid(self._fingerprint, "evidence-prov", self._counter)
        self._records.append(
            generated.ProvenanceRecord(
                id=record_id,
                producer=f"evidence.{MOCK_PROVIDER}",
                producerVersion=MOCK_PROVIDER_VERSION,
                operation=f"region-candidate:{provider_label}",
                inputRefs=list(input_refs),
            )
        )
        self._candidates.append(
            generated.RegionCandidate(
                evidenceType="REGION",
                id=evidence_id,
                pageId=page_id,
                geometry=rect,
                normalizedLabel=normalized_label,
                providerLabel=provider_label,
                textPreview=text_preview or None,
                confidence=confidence,
                provenanceIds=[record_id],
            )
        )

    def finish(self) -> tuple[list[generated.Evidence], generated.ProvenanceStore]:
        return self._candidates, generated.ProvenanceStore(records=self._records)


class MockLayoutEvidenceProvider:
    """Deterministic layout-evidence provider for M3 development and benchmarks.

    Emits REGION candidates (paragraph/heading/caption/table/formula
    guesses) derived from PhysicalDocument geometry and text. Candidates are
    deliberately heuristic and slightly lossy: fusion must weigh provider
    confidence against internal geometric evidence, never trust it blindly.
    """

    name = MOCK_PROVIDER
    version = MOCK_PROVIDER_VERSION

    def __init__(self, fingerprint: str | None = None) -> None:
        self._explicit_fingerprint = fingerprint

    def collect(self, physical: generated.PhysicalDocument) -> generated.EvidenceBundle:
        fingerprint = self._explicit_fingerprint or physical.sourceFingerprint or physical.id
        sink = _CandidateSink(fingerprint)
        body_font_by_page: dict[str, float] = {}
        page_body_spans: dict[str, list[generated.TextSpan]] = {}
        page_headers: dict[str, list[generated.TextSpan]] = {}
        page_footers: dict[str, list[generated.TextSpan]] = {}
        for page in physical.pages:
            spans = [
                obj
                for obj in physical.objects
                if obj.objectType == "textSpan" and obj.pageId == page.id
            ]
            spans.sort(key=_span_order)
            body, headers, footers = split_furniture(spans, page.geometry.heightPt, 0.0)
            page_body_spans[page.id] = body
            page_headers[page.id] = headers
            page_footers[page.id] = footers
            body_font_by_page[page.id] = body_font_size(spans)

        for page in physical.pages:
            body_font = body_font_by_page[page.id]
            for candidate in _paragraph_candidates(page_body_spans[page.id]):
                _emit_region_candidate(sink, candidate, body_font)
            for rect, preview in _table_candidates(page_body_spans[page.id]):
                sink.add_region(
                    page_id=page.id,
                    rect=rect,
                    normalized_label="TABLE",
                    provider_label="table",
                    confidence=0.6,
                    text_preview=preview,
                    input_refs=[],
                )
            for kind, spans in (
                ("header", page_headers[page.id]),
                ("footer", page_footers[page.id]),
            ):
                for span in spans:
                    sink.add_region(
                        page_id=page.id,
                        rect=as_rect(span.geometry),
                        normalized_label=kind.upper(),  # type: ignore[arg-type]
                        provider_label=kind,
                        confidence=0.6,
                        text_preview=span.text[:200],
                        input_refs=[span.id],
                    )
        candidates, provenance = sink.finish()
        return generated.EvidenceBundle(
            schemaVersion="0.1.0",
            provider=self.name,
            providerVersion=self.version,
            candidates=candidates,
            provenance=provenance,
        )


def _span_order(span: generated.TextSpan) -> tuple[float, float]:
    rect = as_rect(span.geometry)
    return (rect.y, rect.x)


def _font_size(span: generated.TextSpan) -> float:
    if span.fontSize is not None and span.fontSize > 0:
        return span.fontSize
    return as_rect(span.geometry).height


def _paragraph_candidates(
    spans: list[generated.TextSpan],
) -> list[list[generated.TextSpan]]:
    """Cluster lines into paragraph-like candidates.

    Slightly looser than the internal geometric blocking (larger gap
    tolerance) so fusion has genuine work: provider candidates may span a
    paragraph that internal blocking split, and vice versa. Chaining uses
    the previous LINE (not the cluster union) so a full-width line cannot
    bridge two columns into one candidate.
    """
    clusters: list[list[generated.TextSpan]] = []
    for span in spans:
        rect = as_rect(span.geometry)
        height = rect.height or 1.0
        best: list[generated.TextSpan] | None = None
        best_gap = float("inf")
        for cluster in clusters:
            last_rect = as_rect(cluster[-1].geometry)
            if overlap_ratio(last_rect, rect) < PARA_MIN_X_OVERLAP:
                continue
            gap = vertical_gap(last_rect, rect)
            max_gap = max(6.0, PARA_MAX_GAP_FACTOR * max(height, last_rect.height))
            if gap <= max_gap and gap < best_gap:
                best = cluster
                best_gap = gap
        if best is None:
            clusters.append([span])
        else:
            best.append(span)
    return clusters


def _cluster_rect(cluster: list[generated.TextSpan]) -> generated.Rect:
    rect = as_rect(cluster[0].geometry)
    for span in cluster[1:]:
        rect = union_rect(rect, as_rect(span.geometry))
    return rect


# Table detection (deterministic baseline). PDFium merges table rows into
# single text spans when cell gaps are small, so cell-level structure is
# often unrecoverable here; real TABLE_STRUCTURE evidence needs a parser
# like MinerU. Baseline signal: a run of >= 3 consecutive lines with
# identical x-extent where most lines end in numeric tokens (data rows).
TABLE_MIN_ROWS = 3
TABLE_ALIGN_TOLERANCE_PT = 2.5
TABLE_ROW_GAP_FACTOR = 3.0
TABLE_NUMERIC_ROW_RATIO = 0.5
_NUMERIC_TAIL = re.compile(r"[\d.,%]+\)?\s*$")


def _table_candidates(
    spans: list[generated.TextSpan],
) -> list[tuple[generated.Rect, str]]:
    ordered = sorted(spans, key=lambda span: (as_rect(span.geometry).y, as_rect(span.geometry).x))
    candidates: list[tuple[generated.Rect, str]] = []
    run: list[generated.TextSpan] = []

    def flush() -> None:
        nonlocal run
        if len(run) >= TABLE_MIN_ROWS:
            numeric_rows = sum(1 for span in run if _NUMERIC_TAIL.search(span.text.strip()))
            if numeric_rows / len(run) >= TABLE_NUMERIC_ROW_RATIO:
                rect = _cluster_rect(run)
                candidates.append((rect, " ".join(span.text for span in run)[:200]))
        run = []

    for span in ordered:
        rect = as_rect(span.geometry)
        if run:
            prev = run[-1]
            prev_rect = as_rect(prev.geometry)
            aligned = (
                abs(rect.x - prev_rect.x) <= TABLE_ALIGN_TOLERANCE_PT
                and abs(rect.x + rect.width - (prev_rect.x + prev_rect.width))
                <= TABLE_ALIGN_TOLERANCE_PT
            )
            gap = rect.y - (prev_rect.y + prev_rect.height)
            contiguous = 0 <= gap <= TABLE_ROW_GAP_FACTOR * max(rect.height, prev_rect.height, 1.0)
            if not (aligned and contiguous):
                flush()
        run.append(span)
    flush()
    return candidates


def _emit_region_candidate(
    sink: _CandidateSink,
    cluster: list[generated.TextSpan],
    body_font: float,
) -> None:
    """Label and emit one paragraph-cluster candidate.

    Label precedence mirrors scholarly layout: caption prefix beats font
    size (captions are often small but distinctive), formulas and tables
    are recognized from content shape, headings from font size.
    """
    rect = _cluster_rect(cluster)
    text = " ".join(span.text for span in cluster)
    font_size = max(_font_size(span) for span in cluster)
    input_refs = [span.id for span in cluster]
    page_id = cluster[0].pageId

    if _CAPTION_PREFIX.match(text):
        sink.add_region(
            page_id=page_id,
            rect=rect,
            normalized_label="CAPTION_LIKE",
            provider_label="caption",
            confidence=0.75,
            text_preview=text[:200],
            input_refs=input_refs,
        )
        return

    if _looks_like_formula(text):
        sink.add_region(
            page_id=page_id,
            rect=rect,
            normalized_label="FORMULA",
            provider_label="formula",
            confidence=0.5,
            text_preview=text[:200],
            input_refs=input_refs,
        )
        return

    if body_font > 0 and font_size / body_font >= 1.15 and len(text) <= 120:
        sink.add_region(
            page_id=page_id,
            rect=rect,
            normalized_label="HEADING_LIKE",
            provider_label="title",
            confidence=0.65,
            text_preview=text[:200],
            input_refs=input_refs,
        )
        return

    sink.add_region(
        page_id=page_id,
        rect=rect,
        normalized_label="PARAGRAPH_LIKE",
        provider_label="para",
        confidence=0.6,
        text_preview=text[:200],
        input_refs=input_refs,
    )


def _looks_like_formula(text: str) -> bool:
    """Formula guess: math-symbol dense and short."""
    if not text or len(text) > 200:
        return False
    stripped = text.strip()
    if stripped.count("=") + stripped.count("\\") == 0:
        return False
    math_chars = sum(1 for char in stripped if char in _FORMULA_CHARS)
    return math_chars / len(stripped) >= 0.25
