"""Phase 3.1 evidence normalization: provider candidates -> comparable form.

Third-party parser adapters emit :class:`~document_model.generated.EvidenceBundle`
candidates whose labels and coordinates are provider-specific. Normalization
maps them into the shared vocabulary (``LayoutLabel``) and canonical page
space so that Region Fusion (Phase 3.2) can compare candidates from
different providers on equal footing. Provider schemas never leak past this
boundary (see docs/contracts/parser-adapter-contract.md).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from document_model import load_document
from document_model.generated import schema_models as generated

from pdf_pipeline.geometry import as_rect

# Canonical LayoutLabel identity entries keep normalization idempotent:
# candidates that already carry a normalized label pass through unchanged.
_CANONICAL_LABELS = (
    "TEXT",
    "HEADING_LIKE",
    "PARAGRAPH_LIKE",
    "CAPTION_LIKE",
    "FIGURE",
    "TABLE",
    "FORMULA",
    "FOOTNOTE",
    "HEADER",
    "FOOTER",
    "LIST",
    "UNKNOWN",
)

# Provider label -> canonical LayoutLabel. Keys are matched case-insensitively
# after stripping; adapters for new providers register their native labels
# here instead of inventing new layout vocabulary.
_LABEL_MAP: dict[str, generated.LayoutLabel] = {
    **{canonical: canonical for canonical in _CANONICAL_LABELS},
    # mock provider native labels
    "para": "PARAGRAPH_LIKE",
    "paragraph": "PARAGRAPH_LIKE",
    "title": "HEADING_LIKE",
    "heading": "HEADING_LIKE",
    "section-heading": "HEADING_LIKE",
    "caption": "CAPTION_LIKE",
    "figure": "FIGURE",
    "image": "FIGURE",
    "table": "TABLE",
    "formula": "FORMULA",
    "equation": "FORMULA",
    "footnote": "FOOTNOTE",
    "header": "HEADER",
    "footer": "FOOTER",
    "list": "LIST",
    "text": "TEXT",
    # common MinerU-style native labels (forward compatibility)
    "plain text": "PARAGRAPH_LIKE",
    "display_formula": "FORMULA",
    "abandon": "UNKNOWN",
}

# Quantization step (PDF points) for candidate matching keys. Candidates
# whose geometry differs by less than this are treated as co-located.
MATCH_KEY_QUANTUM_PT = 1.0


@dataclass(frozen=True)
class NormalizedCandidate:
    """A provider candidate in canonical form, ready for fusion."""

    evidenceId: str
    pageId: str
    rect: generated.Rect
    label: generated.LayoutLabel
    providerLabel: str
    provider: str
    confidence: float
    textPreview: str
    provenanceIds: tuple[str, ...]

    def match_key(self) -> tuple[str, float, float, str]:
        """Co-location key shared across providers for candidate matching."""
        return (
            self.pageId,
            round(self.rect.x / MATCH_KEY_QUANTUM_PT),
            round(self.rect.y / MATCH_KEY_QUANTUM_PT),
            self.label,
        )


def normalize_label(provider_label: str) -> generated.LayoutLabel:
    """Map a provider-native label onto the shared LayoutLabel vocabulary."""
    key = provider_label.strip().lower()
    if key in _LABEL_MAP:
        return _LABEL_MAP[key]
    if key.upper() in _LABEL_MAP:
        return _LABEL_MAP[key.upper()]
    return cast("generated.LayoutLabel", "UNKNOWN")


def normalize_geometry(
    geometry: generated.Geometry,
    page: generated.PhysicalPage,
    *,
    provider_space: generated.Matrix | None = None,
) -> generated.Rect:
    """Normalize provider geometry into canonical page space as a rect.

    ``provider_space`` maps provider coordinates into canonical page space.
    Providers that already emit canonical coordinates pass ``None``. The
    result is narrowed to the bounding rect: v0.1 layout recovery is
    axis-aligned.
    """
    rect = as_rect(geometry)
    if provider_space is None:
        return rect
    m = provider_space
    corners = [
        (m.a * x + m.c * y + m.e, m.b * x + m.d * y + m.f)
        for x, y in (
            (rect.x, rect.y),
            (rect.x + rect.width, rect.y),
            (rect.x, rect.y + rect.height),
            (rect.x + rect.width, rect.y + rect.height),
        )
    ]
    xs = [point[0] for point in corners]
    ys = [point[1] for point in corners]
    x, y = min(xs), min(ys)
    return generated.Rect(kind="rect", x=x, y=y, width=max(xs) - x, height=max(ys) - y)


def normalize_bundle(
    bundle: generated.EvidenceBundle,
    physical: generated.PhysicalDocument,
) -> list[NormalizedCandidate]:
    """Normalize every region-like candidate of an evidence bundle.

    Structure/Metadata candidates carry document-level hints without page
    geometry and are consumed by semantic recovery (M4), not layout fusion;
    they are skipped here. Table/Formula/Region candidates all describe page
    geometry and are normalized for fusion. Malformed candidates (unknown
    page, empty geometry) are dropped: providers may be wrong, the layout
    layer must stay structurally sound.
    """
    pages = {page.id: page for page in physical.pages}
    normalized: list[NormalizedCandidate] = []
    for candidate in bundle.candidates:
        if not isinstance(
            candidate,
            generated.RegionCandidate | generated.TableCandidate | generated.FormulaCandidate,
        ):
            continue
        page = pages.get(candidate.pageId)
        if page is None:
            continue
        rect = normalize_geometry(candidate.geometry, page)
        if rect.width <= 0 or rect.height <= 0:
            continue
        if isinstance(candidate, generated.RegionCandidate):
            label = normalize_label(candidate.normalizedLabel)
            provider_label = candidate.providerLabel
            text_preview = candidate.textPreview or ""
        else:
            label = cast(
                "generated.LayoutLabel",
                "TABLE" if isinstance(candidate, generated.TableCandidate) else "FORMULA",
            )
            provider_label = label
            if isinstance(candidate, generated.FormulaCandidate):
                text_preview = candidate.unicodeText or candidate.rawText or candidate.latex or ""
            else:
                text_preview = ""
        normalized.append(
            NormalizedCandidate(
                evidenceId=candidate.id,
                pageId=candidate.pageId,
                rect=rect,
                label=label,
                providerLabel=provider_label,
                provider=bundle.provider,
                confidence=candidate.confidence,
                textPreview=text_preview,
                provenanceIds=tuple(candidate.provenanceIds),
            )
        )
    return normalized


def evidence_bundle_from_json(data: object) -> generated.EvidenceBundle:
    """Load and validate an EvidenceBundle from parsed JSON."""
    return cast(
        "generated.EvidenceBundle",
        load_document("evidence", cast("dict[str, object]", data)),
    )
