"""Phase 1.3 validation: Evidence schema and provider isolation.

Fake adapters prove that recovery code only needs the unified evidence
schema, never provider-specific formats.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

import document_model.generated.schema_models as m
import pytest
from document_model import dump_document, load_document, new_id

SCHEMA_ROOT = Path(__file__).resolve().parents[4] / "schemas"


class FakeEvidenceAdapter(Protocol):
    """Adapter contract: provider payload in, canonical EvidenceBundle out."""

    provider: str

    def adapt(self, payload: dict[str, Any]) -> m.EvidenceBundle: ...


class FakeMinerUAdapter:
    """Mimics MinerU: middle-panel layout blocks, display_formula labels."""

    provider = "mineru"

    def __init__(self, page_id: str, provenance_id: str) -> None:
        self.page_id = page_id
        self.provenance_id = provenance_id

    def adapt(self, payload: dict[str, Any]) -> m.EvidenceBundle:
        candidates: list[m.Evidence] = [
            m.RegionCandidate(
                evidenceType="REGION",
                id=new_id(),
                pageId=self.page_id,
                geometry=m.Rect(
                    kind="rect",
                    **{k: float(v) for k, v in block["bbox"].items()},
                ),
                normalizedLabel="FORMULA" if block["type"] == "display_formula" else "TEXT",
                providerLabel=block["type"],
                confidence=0.88,
                provenanceIds=[self.provenance_id],
            )
            for block in payload.get("middle", {}).get("para_blocks", [])
        ]
        return m.EvidenceBundle(
            schemaVersion="0.1.0",
            provider=self.provider,
            providerVersion="2.5.4",
            candidates=candidates,
        )


class FakeDoclingAdapter:
    """Mimics Docling: flat items with FORMULA/FORMULA label semantics."""

    provider = "docling"

    def __init__(self, page_id: str, provenance_id: str) -> None:
        self.page_id = page_id
        self.provenance_id = provenance_id

    def adapt(self, payload: dict[str, Any]) -> m.EvidenceBundle:
        candidates: list[m.Evidence] = [
            m.RegionCandidate(
                evidenceType="REGION",
                id=new_id(),
                pageId=self.page_id,
                geometry=m.Rect(kind="rect", **item["bbox"]),
                normalizedLabel="FORMULA" if item["label"] == "FORMULA" else "TEXT",
                providerLabel=item["label"],
                confidence=0.8,
                provenanceIds=[self.provenance_id],
            )
            for item in payload.get("texts", [])
        ]
        return m.EvidenceBundle(
            schemaVersion="0.1.0",
            provider=self.provider,
            providerVersion="1.2.0",
            candidates=candidates,
        )


@pytest.mark.unit
def test_evidence_fixture_roundtrip(evidence_data: dict[str, Any]) -> None:
    bundle = load_document("evidence", evidence_data)
    assert dump_document(bundle) == evidence_data


@pytest.mark.unit
def test_mineru_display_formula_maps_to_unified_label() -> None:
    adapter = FakeMinerUAdapter(new_id(), new_id())
    payload = {
        "middle": {
            "para_blocks": [
                {"type": "display_formula", "bbox": {"x": 10, "y": 20, "width": 100, "height": 30}},
                {"type": "text", "bbox": {"x": 10, "y": 60, "width": 100, "height": 40}},
            ]
        }
    }
    bundle = adapter.adapt(payload)
    regions = [c for c in bundle.candidates if isinstance(c, m.RegionCandidate)]
    labels = {c.providerLabel: c.normalizedLabel for c in regions}
    assert labels["display_formula"] == "FORMULA"


@pytest.mark.unit
def test_docling_formula_maps_to_unified_label() -> None:
    adapter = FakeDoclingAdapter(new_id(), new_id())
    payload = {
        "texts": [
            {"label": "FORMULA", "bbox": {"x": 5, "y": 5, "width": 50, "height": 20}},
            {"label": "paragraph", "bbox": {"x": 5, "y": 35, "width": 50, "height": 20}},
        ]
    }
    bundle = adapter.adapt(payload)
    regions = [c for c in bundle.candidates if isinstance(c, m.RegionCandidate)]
    labels = {c.providerLabel: c.normalizedLabel for c in regions}
    assert labels["FORMULA"] == "FORMULA"
    assert labels["paragraph"] == "TEXT"


@pytest.mark.unit
def test_recovery_consumes_only_unified_schema() -> None:
    """A recovery-style consumer reads candidates without provider imports."""

    def recover_regions(bundle: m.EvidenceBundle) -> list[str]:
        return [c.normalizedLabel for c in bundle.candidates if c.evidenceType == "REGION"]

    adapter = FakeDoclingAdapter(new_id(), new_id())
    bundle = adapter.adapt(
        {"texts": [{"label": "paragraph", "bbox": {"x": 1, "y": 2, "width": 3, "height": 4}}]}
    )
    assert recover_regions(bundle) == ["TEXT"]


@pytest.mark.unit
def test_provider_specific_schema_never_leaks() -> None:
    """EvidenceBundle forbids extra keys, so raw provider payloads cannot pass."""
    raw: dict[str, Any] = {
        "schemaVersion": "0.1.0",
        "provider": "mineru",
        "providerVersion": "2.5.4",
        "candidates": [],
        "middle": {"para_blocks": []},  # provider-specific key
    }
    with pytest.raises(Exception, match="middle"):
        m.EvidenceBundle.model_validate(raw)


@pytest.mark.unit
def test_formula_candidate_keeps_fallback_text(evidence_data: dict[str, Any]) -> None:
    bundle = m.EvidenceBundle.model_validate(evidence_data)
    formulas = [c for c in bundle.candidates if c.evidenceType == "FORMULA"]
    assert formulas, "fixture must include a formula candidate"
    formula = formulas[0]
    assert formula.latex is None
    assert formula.mathml is None
    assert formula.rawText == "E = m c^2"


@pytest.mark.unit
def test_structure_candidate_is_unified_evidence(evidence_data: dict[str, Any]) -> None:
    bundle = m.EvidenceBundle.model_validate(evidence_data)
    structures = [c for c in bundle.candidates if c.evidenceType == "STRUCTURE"]
    assert structures, "fixture must include a structure candidate"
    assert structures[0].role == "SECTION"
