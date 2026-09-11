"""Phase 7.3 Adaptive Parser Routing: probe-driven provider selection.

Not every parser runs on every document (docs/architecture
/document-architecture.md §42). The routing plan is a deterministic
function of the DocumentProbe result and the Capability Registry:
the layout primary always runs, table-dense documents additionally wake
the table-structure specialist, and scholarly metadata/bibliography runs
on every born-digital paper. Scanned documents never reach routing (the
input capability gate fails loudly upstream).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from pdf_pipeline.capabilities import load_registry
from pdf_pipeline.evidence.fake_specialists import (
    FakeDoclingTableProvider,
    FakeGrobidScholarlyProvider,
)
from pdf_pipeline.evidence.providers import EvidenceProvider, MockLayoutEvidenceProvider

if TYPE_CHECKING:
    from document_model.generated import schema_models as generated

    from pdf_pipeline.capabilities import Registry
    from pdf_pipeline.probe import ProbeResult

ROUTING_VERSION = "0.1.0"

# A document routes the table specialist when at least this share of its
# pages contains table-like aligned rows.
TABLE_DENSITY_THRESHOLD = 0.1

# A document is math-heavy when math symbols carry at least this share of
# all extracted characters; the formula capability then belongs to the run.
MATH_DENSITY_THRESHOLD = 0.05


@dataclass(frozen=True)
class RouteDecision:
    """One routed provider with the capabilities it covers and why."""

    provider: str
    capabilities: tuple[str, ...]
    reason: str

    def to_json(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "capabilities": list(self.capabilities),
            "reason": self.reason,
        }


@dataclass(frozen=True)
class RoutingPlan:
    """The deterministic provider selection for one document."""

    decisions: tuple[RouteDecision, ...]

    def provider_names(self) -> tuple[str, ...]:
        return tuple(decision.provider for decision in self.decisions)

    def to_json(self) -> list[dict[str, object]]:
        return [decision.to_json() for decision in self.decisions]


def route_providers(
    probe: ProbeResult,
    registry: Registry | None = None,
) -> RoutingPlan:
    """Select the evidence providers to run for a probed document."""
    registry = registry if registry is not None else load_registry()
    if probe.native_text_ratio == 0.0:
        raise ValueError(
            "document has no native text layer on any page "
            "(scanned PDFs are not supported; the document may need OCR)"
        )

    layout_capability = registry["layout.region"]
    layout_reason = f"layout.region primary {layout_capability.primary}"
    layout_capabilities = ["layout.region"]
    if probe.math_density >= MATH_DENSITY_THRESHOLD:
        layout_capabilities.append(registry["formula.detection"].name)
        layout_reason += f"; math density {probe.math_density:.2f} >= {MATH_DENSITY_THRESHOLD}"
    if probe.estimated_columns is not None and probe.estimated_columns > 1:
        layout_reason += f"; estimated columns {probe.estimated_columns}"
    decisions = [
        RouteDecision(
            provider=layout_capability.primary,
            capabilities=tuple(layout_capabilities),
            reason=layout_reason,
        )
    ]

    if probe.table_density >= TABLE_DENSITY_THRESHOLD:
        table_structure = registry["table.structure"].primary
        if table_structure != layout_capability.primary:
            decisions.append(
                RouteDecision(
                    provider=table_structure,
                    capabilities=("table.structure", "table.detection"),
                    reason=(
                        f"table density {probe.table_density:.2f} >= {TABLE_DENSITY_THRESHOLD}"
                    ),
                )
            )

    scholarly = registry["scholarly.metadata"].primary
    decisions.append(
        RouteDecision(
            provider=scholarly,
            capabilities=("scholarly.metadata", "scholarly.bibliography"),
            reason="scholarly metadata/bibliography primary (standard paper route)",
        )
    )
    return RoutingPlan(tuple(decisions))


def build_provider(name: str, fingerprint: str | None = None) -> EvidenceProvider:
    """Instantiate the provider implementation behind a registry name."""
    if name == "mock":
        return MockLayoutEvidenceProvider(fingerprint)
    if name == "docling-sim":
        return FakeDoclingTableProvider(fingerprint)
    if name == "grobid-sim":
        return FakeGrobidScholarlyProvider(fingerprint)
    raise KeyError(f"no provider implementation registered for {name!r}")


def collect_bundles(
    plan: RoutingPlan,
    physical: generated.PhysicalDocument,
) -> list[generated.EvidenceBundle]:
    """Run every routed provider once, in plan order."""
    fingerprint = physical.sourceFingerprint or physical.id
    return [
        build_provider(decision.provider, fingerprint).collect(physical)
        for decision in plan.decisions
    ]
