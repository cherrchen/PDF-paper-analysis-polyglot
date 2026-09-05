"""Evidence adapter boundary (Roadmap M3 Phase 3.1).

Third-party parsers never speak our document model directly: providers emit
canonical :class:`~document_model.generated.EvidenceBundle` candidates,
normalization maps them onto the shared label vocabulary and canonical page
space, and layout fusion consumes only the normalized form.
"""

from __future__ import annotations

from pdf_pipeline.evidence.normalize import (
    NormalizedCandidate,
    evidence_bundle_from_json,
    normalize_bundle,
    normalize_geometry,
    normalize_label,
)
from pdf_pipeline.evidence.providers import (
    MOCK_PROVIDER,
    MOCK_PROVIDER_VERSION,
    EvidenceProvider,
    MockLayoutEvidenceProvider,
)

__all__ = [
    "MOCK_PROVIDER",
    "MOCK_PROVIDER_VERSION",
    "EvidenceProvider",
    "MockLayoutEvidenceProvider",
    "NormalizedCandidate",
    "evidence_bundle_from_json",
    "normalize_bundle",
    "normalize_geometry",
    "normalize_label",
]
