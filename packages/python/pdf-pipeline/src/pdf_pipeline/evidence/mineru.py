"""MinerU native dump adapter (layout / formula evidence).

Maps recorded MinerU 2.x-style JSON (``pdf_info`` pages or the older
``middle.para_blocks`` shape) into a canonical EvidenceBundle. Live
invocation is optional via ``MINERU_CMD`` + ``PAPER_SOURCE_PDF`` and is
never the default CI path.
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
    page_id_at,
    parse_rect,
)
from pdf_pipeline.evidence.providers import CandidateSink

if TYPE_CHECKING:
    from pathlib import Path

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
        return load_provider_json(
            self.name,
            fingerprint,
            dump_env=MINERU_DUMP_ENV,
            explicit=self._dump_path,
            live=lambda: collect_live_json(MINERU_CMD_ENV),
            live_hint=f"{MINERU_CMD_ENV} + PAPER_SOURCE_PDF",
        )


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
            mapping = as_mapping(block)
            if mapping is None:
                continue
            _emit_block(sink, page_id, block_index, mapping)
    candidates, provenance = sink.finish()
    return generated.EvidenceBundle(
        schemaVersion="0.1.0",
        provider=MINERU_PROVIDER,
        providerVersion=MINERU_PROVIDER_VERSION,
        candidates=candidates,
        provenance=provenance,
    )


def _iter_page_blocks(payload: dict[str, Any]) -> list[tuple[int, list[object]]]:
    pages: list[tuple[int, list[object]]] = []
    pdf_info = as_list(payload.get("pdf_info"))
    if pdf_info:
        for index, page in enumerate(pdf_info):
            mapping = as_mapping(page)
            if mapping is None:
                continue
            page_index = index
            raw_index = mapping.get("page_idx")
            if isinstance(raw_index, int) and not isinstance(raw_index, bool):
                page_index = raw_index
            blocks = as_list(mapping.get("para_blocks") or mapping.get("preproc_blocks"))
            pages.append((page_index, blocks))
        return pages
    middle = as_mapping(payload.get("middle"))
    if middle is not None:
        return [(0, as_list(middle.get("para_blocks")))]
    blocks = as_list(payload.get("para_blocks"))
    if blocks:
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
            "id": sink.derived_id(f"formula-{page_id}-{block_index}"),
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
    for line in as_list(block.get("lines")):
        mapping = as_mapping(line)
        if mapping is None:
            continue
        for span in as_list(mapping.get("spans")):
            span_map = as_mapping(span)
            content = span_map.get("content") if span_map is not None else None
            if isinstance(content, str):
                parts.append(content)
    return " ".join(parts).strip()
