"""Docling native dump adapter (table structure + layout challenger).

Maps recorded Docling JSON (``texts`` / ``tables`` items) into REGION and
TABLE_STRUCTURE candidates. Live invocation is optional via ``DOCLING_CMD``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from document_model.generated import schema_models as generated

from pdf_pipeline.evidence.native import (
    as_list,
    as_mapping,
    collect_live_json,
    label_for,
    load_provider_json,
    page_height_at,
    page_id_at,
    parse_rect,
)
from pdf_pipeline.evidence.providers import CandidateSink

if TYPE_CHECKING:
    from pathlib import Path

DOCLING_PROVIDER = "docling"
DOCLING_PROVIDER_VERSION = "2.x-dump"
DOCLING_DUMP_ENV = "DOCLING_DUMP"
DOCLING_CMD_ENV = "DOCLING_CMD"

_REGION_CONFIDENCE = 0.8
_TABLE_CONFIDENCE = 0.88


class DoclingEvidenceProvider:
    """EvidenceProvider for recorded (or optionally live) Docling output."""

    name = DOCLING_PROVIDER
    version = DOCLING_PROVIDER_VERSION

    def __init__(
        self,
        fingerprint: str | None = None,
        *,
        payload: dict[str, Any] | None = None,
        dump_path: Path | None = None,
    ) -> None:
        self._explicit_fingerprint = fingerprint
        self._payload = payload
        self._dump_path = dump_path

    def collect(self, physical: generated.PhysicalDocument) -> generated.EvidenceBundle:
        fingerprint = self._explicit_fingerprint or physical.sourceFingerprint or physical.id
        payload = self._payload if self._payload is not None else self._load_payload(fingerprint)
        return adapt_docling_payload(payload, physical, fingerprint)

    def _load_payload(self, fingerprint: str) -> dict[str, Any]:
        return load_provider_json(
            self.name,
            fingerprint,
            dump_env=DOCLING_DUMP_ENV,
            explicit=self._dump_path,
            live=lambda: collect_live_json(DOCLING_CMD_ENV),
            live_hint=f"{DOCLING_CMD_ENV} + PAPER_SOURCE_PDF",
        )


def adapt_docling_payload(
    payload: dict[str, Any],
    physical: generated.PhysicalDocument,
    fingerprint: str,
) -> generated.EvidenceBundle:
    """Map a Docling-native JSON object to EvidenceBundle."""
    sink = CandidateSink(fingerprint, DOCLING_PROVIDER, DOCLING_PROVIDER_VERSION, "docling:")
    for item in as_list(payload.get("texts")):
        mapping = as_mapping(item)
        if mapping is None:
            continue
        page_index, rect = _item_location(mapping, physical)
        provider_label = str(mapping.get("label") or "paragraph")
        sink.add_region(
            page_id=page_id_at(physical, page_index),
            rect=rect,
            normalized_label=label_for(provider_label),
            provider_label=provider_label,
            confidence=_REGION_CONFIDENCE,
            text_preview=str(mapping.get("text") or "")[:200],
        )
    for index, table in enumerate(as_list(payload.get("tables"))):
        mapping = as_mapping(table)
        if mapping is None:
            continue
        _emit_table(sink, physical, index, mapping)
    candidates, provenance = sink.finish()
    return generated.EvidenceBundle(
        schemaVersion="0.1.0",
        provider=DOCLING_PROVIDER,
        providerVersion=DOCLING_PROVIDER_VERSION,
        candidates=candidates,
        provenance=provenance,
    )


def _emit_table(
    sink: CandidateSink,
    physical: generated.PhysicalDocument,
    index: int,
    table: dict[str, Any],
) -> None:
    page_index, rect = _item_location(table, physical)
    data = as_mapping(table.get("data")) or table
    cells = _table_cells(data)
    row_count = _as_count(data.get("num_rows"))
    column_count = _as_count(data.get("num_cols"))
    if not row_count and cells:
        row_count = max(cell.row + cell.rowSpan for cell in cells)
    if not column_count and cells:
        column_count = max(cell.column + cell.colSpan for cell in cells)
    sink.add_evidence(
        generated.TableCandidate(
            evidenceType="TABLE_STRUCTURE",
            id=sink.derived_id(f"table-{index}"),
            pageId=page_id_at(physical, page_index),
            geometry=rect,
            rowCount=row_count,
            columnCount=column_count,
            cells=cells,
            confidence=_TABLE_CONFIDENCE,
            provenanceIds=[],
        ),
        operation="docling-table",
    )


def _table_cells(data: dict[str, Any]) -> list[generated.TableCellCandidate]:
    raw_cells = as_list(data.get("table_cells"))
    if raw_cells:
        return [
            cell
            for item in raw_cells
            if (cell := _cell_from_dump(item, fallback_row=0, fallback_column=0)) is not None
        ]
    return _cells_from_grid(as_list(data.get("grid")))


def _cells_from_grid(grid: list[object]) -> list[generated.TableCellCandidate]:
    cells: list[generated.TableCellCandidate] = []
    covered: set[tuple[int, int]] = set()
    for row_index, row in enumerate(grid):
        for column_index, item in enumerate(as_list(row)):
            if (row_index, column_index) in covered:
                continue
            cell = _cell_from_dump(item, fallback_row=row_index, fallback_column=column_index)
            if cell is None:
                continue
            if (row_index, column_index) != (cell.row, cell.column):
                continue
            for span_row in range(cell.row, cell.row + cell.rowSpan):
                for span_col in range(cell.column, cell.column + cell.colSpan):
                    covered.add((span_row, span_col))
            cells.append(cell)
    return cells


def _cell_from_dump(
    item: object,
    *,
    fallback_row: int,
    fallback_column: int,
) -> generated.TableCellCandidate | None:
    mapping = as_mapping(item)
    if mapping is None:
        return None
    row = _as_count(mapping.get("start_row_offset_idx"), mapping.get("row"), fallback_row)
    column = _as_count(mapping.get("start_col_offset_idx"), mapping.get("column"), fallback_column)
    end_row = mapping.get("end_row_offset_idx")
    end_col = mapping.get("end_col_offset_idx")
    row_span = (
        max(_as_count(end_row) - row, 1)
        if end_row is not None
        else max(_as_count(mapping.get("row_span"), mapping.get("rowSpan"), 1), 1)
    )
    col_span = (
        max(_as_count(end_col) - column, 1)
        if end_col is not None
        else max(_as_count(mapping.get("col_span"), mapping.get("colSpan"), 1), 1)
    )
    return generated.TableCellCandidate(
        row=row,
        column=column,
        rowSpan=row_span,
        colSpan=col_span,
        text=str(mapping.get("text") or ""),
    )


def _as_count(*values: object) -> int:
    for value in values:
        if isinstance(value, bool) or value is None:
            continue
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str) and value.strip():
            try:
                return int(value)
            except ValueError:
                continue
    return 0


def _item_location(
    item: dict[str, Any],
    physical: generated.PhysicalDocument,
) -> tuple[int, generated.Rect]:
    prov = as_list(item.get("prov"))
    first = as_mapping(prov[0]) if prov else None
    if first is not None:
        page_index = max(_as_count(first.get("page_no"), first.get("page"), 1) - 1, 0)
        bbox = first.get("bbox") or item.get("bbox")
        return page_index, parse_rect(bbox, page_height=page_height_at(physical, page_index))
    page_index = max(_as_count(item.get("page_idx"), item.get("page"), 0), 0)
    return page_index, parse_rect(
        item.get("bbox"), page_height=page_height_at(physical, page_index)
    )
