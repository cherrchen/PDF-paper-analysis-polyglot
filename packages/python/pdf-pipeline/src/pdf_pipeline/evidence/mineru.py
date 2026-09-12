# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false
"""MinerU native dump adapter (layout / formula evidence).

Maps recorded MinerU 2.x-style JSON (``pdf_info`` pages or the older
``middle.para_blocks`` shape) into a canonical EvidenceBundle. Live
invocation is optional via ``MINERU_CMD`` + ``PAPER_SOURCE_PDF`` and is
never the default CI path.
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

MINERU_PROVIDER = "mineru"
MINERU_PROVIDER_VERSION = "2.x-dump"
MINERU_DUMP_ENV = "MINERU_DUMP"
MINERU_CMD_ENV = "MINERU_CMD"

_FORMULA_LABELS = frozenset({"display_formula", "inline_formula", "equation", "formula"})
_REGION_CONFIDENCE = 0.82
_FORMULA_CONFIDENCE = 0.8


class MinerUEvidenceProvider:
    """EvidenceProvider for recorded (or optionally live) MinerU output."""

    name = MINERU_PROVIDER
    version = MINERU_PROVIDER_VERSION

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
        return adapt_mineru_payload(payload, physical, fingerprint)

    def _load_payload(self, fingerprint: str) -> dict[str, Any]:
        env_dump = os.environ.get(MINERU_DUMP_ENV)
        path = resolve_dump_path(
            self.name, fingerprint, Path(env_dump) if env_dump else self._dump_path
        )
        if path is not None:
            return load_json_dump(path)
        live = _collect_live_mineru()
        if live is not None:
            return live
        msg = (
            "mineru adapter has no dump: set MINERU_DUMP, PAPER_PARSER_DUMP_DIR, "
            "or MINERU_CMD + PAPER_SOURCE_PDF"
        )
        raise FileNotFoundError(msg)


def adapt_mineru_payload(
    payload: dict[str, Any],
    physical: generated.PhysicalDocument,
    fingerprint: str,
) -> generated.EvidenceBundle:
    """Map a MinerU-native JSON object to EvidenceBundle."""
    sink = CandidateSink(fingerprint, MINERU_PROVIDER, MINERU_PROVIDER_VERSION, "mineru:")
    for page_index, blocks in _iter_page_blocks(payload):
        page_id = page_id_at(physical, page_index)
        for block_index, block in enumerate(blocks):
            if not isinstance(block, dict):
                continue
            _emit_block(sink, page_id, block_index, block)
    candidates, provenance = sink.finish()
    return generated.EvidenceBundle(
        schemaVersion="0.1.0",
        provider=MINERU_PROVIDER,
        providerVersion=MINERU_PROVIDER_VERSION,
        candidates=candidates,
        provenance=provenance,
    )


def _iter_page_blocks(payload: dict[str, Any]) -> list[tuple[int, list[Any]]]:
    pdf_info = payload.get("pdf_info")
    if isinstance(pdf_info, list):
        pages: list[tuple[int, list[Any]]] = []
        for index, page in enumerate(pdf_info):
            if not isinstance(page, dict):
                continue
            page_index = int(page.get("page_idx", index))
            blocks = page.get("para_blocks") or page.get("preproc_blocks") or []
            if isinstance(blocks, list):
                pages.append((page_index, blocks))
        return pages
    middle = payload.get("middle")
    if isinstance(middle, dict):
        blocks = middle.get("para_blocks") or []
        if isinstance(blocks, list):
            return [(0, blocks)]
    blocks = payload.get("para_blocks")
    if isinstance(blocks, list):
        return [(0, blocks)]
    return []


def _emit_block(sink: CandidateSink, page_id: str, block_index: int, block: dict[str, Any]) -> None:
    provider_label = str(block.get("type") or block.get("label") or "text")
    bbox = block.get("bbox")
    if bbox is None:
        return
    rect = parse_rect(bbox)
    text = _block_text(block)
    if provider_label.lower() in _FORMULA_LABELS:
        latex_raw = block.get("latex") or block.get("latex_text")
        mathml_raw = block.get("mathml")
        latex = latex_raw.strip() if isinstance(latex_raw, str) else None
        mathml = mathml_raw.strip() if isinstance(mathml_raw, str) else None
        formula: dict[str, object] = {
            "evidenceType": "FORMULA",
            "id": sink.derived_id(f"formula-{block_index}"),
            "pageId": page_id,
            "geometry": rect,
            "rawText": text or latex or "[formula]",
            "confidence": _FORMULA_CONFIDENCE,
            "provenanceIds": [],
        }
        if latex:
            formula["latex"] = latex
        if mathml:
            formula["mathml"] = mathml
        if text:
            formula["unicodeText"] = text
        sink.add_evidence(
            generated.FormulaCandidate.model_validate(formula),
            operation="mineru-formula",
        )
        return
    sink.add_region(
        page_id=page_id,
        rect=rect,
        normalized_label=label_for(provider_label),
        provider_label=provider_label,
        confidence=_REGION_CONFIDENCE,
        text_preview=text[:200],
    )


def _block_text(block: dict[str, Any]) -> str:
    direct = block.get("text") or block.get("content")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    parts: list[str] = []
    for line in block.get("lines") or []:
        if not isinstance(line, dict):
            continue
        parts.extend(
            span["content"]
            for span in line.get("spans") or []
            if isinstance(span, dict) and isinstance(span.get("content"), str)
        )
    return " ".join(parts).strip()


def _collect_live_mineru() -> dict[str, Any] | None:
    command = os.environ.get(MINERU_CMD_ENV)
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
        msg = "MINERU_CMD stdout must be a JSON object"
        raise TypeError(msg)
    return payload
