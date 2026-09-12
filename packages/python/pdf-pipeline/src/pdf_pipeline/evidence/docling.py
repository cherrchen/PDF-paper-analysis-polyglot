# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false
"""Docling native dump adapter (table structure + layout challenger).

Maps recorded Docling JSON (``texts`` / ``tables`` items) into REGION and
TABLE_STRUCTURE candidates. Live invocation is optional via ``DOCLING_CMD``.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from document_model.generated import schema_models as generated

from pdf_pipeline.evidence.native import (
    label_for,
    load_json_dump,
    page_id_at,
    parse_rect,
    resolve_dump_path,
    source_pdf_path,
)
from pdf_pipeline.evidence.providers import CandidateSink

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
        env_dump = os.environ.get(DOCLING_DUMP_ENV)
        path = resolve_dump_path(
            self.name, fingerprint, Path(env_dump) if env_dump else self._dump_path
        )
        if path is not None:
            return load_json_dump(path)
        live = _collect_live_docling()
        if live is not None:
            return live
        msg = (
            "docling adapter has no dump: set DOCLING_DUMP, PAPER_PARSER_DUMP_DIR, "
            "or DOCLING_CMD + PAPER_SOURCE_PDF"
        )
        raise FileNotFoundError(msg)


def adapt_docling_payload(
    payload: dict[str, Any],
    physical: generated.PhysicalDocument,
    fingerprint: str,
) -> generated.EvidenceBundle:
    """Map a Docling-native JSON object to EvidenceBundle."""
    sink = CandidateSink(fingerprint, DOCLING_PROVIDER, DOCLING_PROVIDER_VERSION, "docling:")
    for item in _as_list(payload.get("texts")):
        if not isinstance(item, dict):
            continue
        page_index, rect = _item_location(item)
        provider_label = str(item.get("label") or "paragraph")
        sink.add_region(
            page_id=page_id_at(physical, page_index),
            rect=rect,
            normalized_label=label_for(provider_label),
            provider_label=provider_label,
            confidence=_REGION_CONFIDENCE,
            text_preview=str(item.get("text") or "")[:200],
        )
    for index, table in enumerate(_as_list(payload.get("tables"))):
        if not isinstance(table, dict):
            continue
        _emit_table(sink, physical, index, table)
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
    page_index, rect = _item_location(table)
    data = table.get("data") if isinstance(table.get("data"), dict) else table
    grid = _as_list(data.get("grid") if isinstance(data, dict) else None)
    cells: list[generated.TableCellCandidate] = []
    for row_index, row in enumerate(grid):
        if not isinstance(row, list):
            continue
        for column_index, cell in enumerate(row):
            if not isinstance(cell, dict):
                continue
            cells.append(
                generated.TableCellCandidate(
                    row=int(cell.get("row", row_index)),
                    column=int(cell.get("column", column_index)),
                    rowSpan=max(int(cell.get("row_span") or cell.get("rowSpan") or 1), 1),
                    colSpan=max(int(cell.get("col_span") or cell.get("colSpan") or 1), 1),
                    text=str(cell.get("text") or ""),
                )
            )
    row_count = int(data.get("num_rows", 0)) if isinstance(data, dict) else 0
    column_count = int(data.get("num_cols", 0)) if isinstance(data, dict) else 0
    if not row_count and cells:
        row_count = max(cell.row for cell in cells) + 1
    if not column_count and cells:
        column_count = max(cell.column for cell in cells) + 1
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


def _item_location(item: dict[str, Any]) -> tuple[int, generated.Rect]:
    prov = _as_list(item.get("prov"))
    if prov and isinstance(prov[0], dict):
        first = prov[0]
        page_index = max(int(first.get("page_no") or first.get("page") or 1) - 1, 0)
        bbox = first.get("bbox") or item.get("bbox")
        return page_index, parse_rect(bbox)
    page_index = max(int(item.get("page_idx") or item.get("page") or 0), 0)
    return page_index, parse_rect(item.get("bbox"))


def _as_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _collect_live_docling() -> dict[str, Any] | None:
    command = os.environ.get(DOCLING_CMD_ENV)
    pdf = source_pdf_path()
    if not command or pdf is None:
        return None
    completed = subprocess.run(  # noqa: S603 — user-configured live parser command
        [*command.split(), str(pdf)],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout)
    if not isinstance(payload, dict):
        msg = "DOCLING_CMD stdout must be a JSON object"
        raise TypeError(msg)
    return payload
