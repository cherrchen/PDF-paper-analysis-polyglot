"""Phase 7.3 Adaptive Parser Routing: probe-driven provider selection.

Not every parser runs on every document (docs/architecture
/document-architecture.md §42). The routing plan is a deterministic
function of the DocumentProbe result and the Capability Registry:
the layout primary always runs, table-dense documents additionally wake
the table-structure specialist, and scholarly metadata/bibliography runs
on every born-digital paper. Scanned documents never reach routing (the
input capability gate fails loudly upstream).

Collection (M8 batch D) isolates provider failures: a specialist that
raises degrades one capability, records a :class:`ProviderDegradation`,
and is covered by the registry ``fallback`` provider or by the recovery
engines' internal baseline. The document keeps its remaining nodes; only
a run that collects no bundle at all is a stage failure.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from document_model.generated import schema_models as generated

from pdf_pipeline.capabilities import load_registry
from pdf_pipeline.evidence.docling import DoclingEvidenceProvider
from pdf_pipeline.evidence.fake_specialists import (
    FakeDoclingTableProvider,
    FakeGrobidScholarlyProvider,
)
from pdf_pipeline.evidence.grobid import GrobidEvidenceProvider
from pdf_pipeline.evidence.mineru import MinerUEvidenceProvider
from pdf_pipeline.evidence.providers import EvidenceProvider, MockLayoutEvidenceProvider
from pdf_pipeline.ids import stable_uuid

if TYPE_CHECKING:
    from collections.abc import Sequence

    from pdf_pipeline.capabilities import Registry
    from pdf_pipeline.probe import ProbeResult

ROUTING_VERSION = "0.2.0"

# A document routes the table specialist when at least this share of its
# pages contains table-like aligned rows.
TABLE_DENSITY_THRESHOLD = 0.1

# A document is math-heavy when math symbols carry at least this share of
# all extracted characters; the formula capability then belongs to the run.
MATH_DENSITY_THRESHOLD = 0.05

# A provider exception message is diagnostic, not payload: cap what lands
# in probe.json and in the document's Issue store.
MAX_ERROR_MESSAGE_CHARS = 500

# Capability -> issue taxonomy category, for the Issue a degradation
# produces. Categories are existing IssueCategory members; a degradation
# never invents taxonomy (that would be a schema change).
_CAPABILITY_ISSUE_CATEGORY: dict[str, generated.IssueCategory] = {
    "layout.region": "LAYOUT_REGION",
    "table.detection": "TABLE_RECOVERY",
    "table.structure": "TABLE_RECOVERY",
    "formula.detection": "FORMULA_RECOVERY",
    "formula.recognition": "FORMULA_RECOVERY",
    "scholarly.metadata": "SECTION_STRUCTURE",
    "scholarly.bibliography": "CITATION_RESOLUTION",
}

# Capability -> the internal baseline that covers it once its provider
# failed and no registry fallback substituted it.
_CAPABILITY_FALLBACK_DESCRIPTION: dict[str, str] = {
    "layout.region": "internal geometry blocking",
    "table.detection": "table line-row fallback",
    "table.structure": "table line-row fallback",
    "formula.detection": "raw formula text",
    "formula.recognition": "raw formula text",
    "scholarly.metadata": "front-matter heuristics",
    "scholarly.bibliography": "bibliography text heuristics",
}


def issue_category_for_capability(capabilities: Sequence[str]) -> generated.IssueCategory:
    """Issue category for a routed capability set (first mapped capability)."""
    for capability in capabilities:
        category = _CAPABILITY_ISSUE_CATEGORY.get(capability)
        if category is not None:
            return category
    return "LAYOUT_REGION"


def fallback_description_for_capability(capabilities: Sequence[str]) -> str:
    """Internal baseline covering a degraded capability set."""
    for capability in capabilities:
        description = _CAPABILITY_FALLBACK_DESCRIPTION.get(capability)
        if description is not None:
            return description
    return "internal baseline"


def _truncate_message(text: str) -> str:
    if len(text) <= MAX_ERROR_MESSAGE_CHARS:
        return text
    return text[:MAX_ERROR_MESSAGE_CHARS] + "..."


@dataclass(frozen=True)
class ProviderDegradation:
    """One failed routed provider and how the run covered for it.

    Field names are the ``probe.json`` keys; ``to_json`` is the only place
    the camelCase spelling surfaces. ``substitutes`` lists the fallback
    providers that actually produced a bundle for the lost capabilities —
    a provider already collected for another capability is reused, never
    rerun, so it appears here too.
    """

    provider: str
    capabilities: tuple[str, ...]
    substitutes: tuple[str, ...]
    errorType: str
    message: str

    def to_json(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "capabilities": list(self.capabilities),
            "substitutes": list(self.substitutes),
            "category": issue_category_for_capability(self.capabilities),
            "errorType": self.errorType,
            "message": self.message,
        }

    def issue_message(self) -> str:
        message = (
            f"evidence provider {self.provider!r} failed for "
            f"{', '.join(self.capabilities)}: {self.message}"
        )
        if self.substitutes:
            message += f"; substituted by {', '.join(self.substitutes)}"
        return message

    def to_issue(self, document_id: str) -> generated.Issue:
        """Canonical Issue for this degradation, attributed to the provider."""
        if self.substitutes:
            fallback = f"provider substitution: {', '.join(self.substitutes)}"
        else:
            fallback = fallback_description_for_capability(self.capabilities)
        return generated.Issue(
            id=stable_uuid(
                document_id, "issue", self.provider, ",".join(self.capabilities), self.message
            ),
            category=issue_category_for_capability(self.capabilities),
            severity="ERROR",
            producer=self.provider,
            message=self.issue_message(),
            affectedIds=[],
            recoverable=True,
            fallback=fallback,
        )


@dataclass(frozen=True)
class ProviderCollection:
    """Routed evidence bundles plus the provider failures that shaped them."""

    bundles: tuple[generated.EvidenceBundle, ...]
    degradations: tuple[ProviderDegradation, ...]

    @property
    def degraded(self) -> bool:
        return bool(self.degradations)

    def issues(self, document_id: str) -> list[generated.Issue]:
        return [degradation.to_issue(document_id) for degradation in self.degradations]


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
    if name == "mineru":
        return MinerUEvidenceProvider(fingerprint)
    if name == "docling":
        return DoclingEvidenceProvider(fingerprint)
    if name == "grobid":
        return GrobidEvidenceProvider(fingerprint)
    raise KeyError(f"no provider implementation registered for {name!r}")


def _attempt(
    name: str,
    physical: generated.PhysicalDocument,
    fingerprint: str,
    *,
    collected: dict[str, generated.EvidenceBundle],
    attempted: set[str],
    failures: dict[str, BaseException],
) -> BaseException | None:
    """Collect one provider at most once; the provider boundary swallows failures.

    Returns the raised exception instead of propagating it: one specialist
    must never break the document (M8 batch D). A provider routed for more
    than one capability set is attempted once; a repeated call re-reports
    the recorded failure rather than claiming success.
    """
    recorded = failures.get(name)
    if recorded is not None:
        return recorded
    if name in attempted:
        return None
    attempted.add(name)
    try:
        collected[name] = build_provider(name, fingerprint).collect(physical)
    except Exception as error:  # the provider boundary: never break the document
        failures[name] = error
        return error
    return None


def _degradation(
    provider: str,
    capabilities: Sequence[str],
    substitutes: tuple[str, ...],
    error: BaseException,
) -> ProviderDegradation:
    error_type = type(error).__name__
    return ProviderDegradation(
        provider=provider,
        capabilities=tuple(capabilities),
        substitutes=substitutes,
        errorType=error_type,
        message=f"{error_type}: {_truncate_message(str(error))}",
    )


def collect_bundles(
    plan: RoutingPlan,
    physical: generated.PhysicalDocument,
    registry: Registry | None = None,
) -> ProviderCollection:
    """Run every routed provider once, in plan order, isolating failures.

    A provider that raises degrades only its own capabilities: the run
    records a :class:`ProviderDegradation`, substitutes the registry
    ``fallback`` provider when one exists (each name is attempted at most
    once per run, and a provider already collected for another capability
    is reused rather than rerun), and otherwise leaves the recovery
    engines to their internal baselines. Bundle order is plan order
    followed by substitution order.
    """
    registry = registry if registry is not None else load_registry()
    fingerprint = physical.sourceFingerprint or physical.id
    collected: dict[str, generated.EvidenceBundle] = {}
    attempted: set[str] = set()
    failures: dict[str, BaseException] = {}
    degradations: list[ProviderDegradation] = []
    for decision in plan.decisions:
        failure = _attempt(
            decision.provider,
            physical,
            fingerprint,
            collected=collected,
            attempted=attempted,
            failures=failures,
        )
        if failure is None:
            continue
        substitutes: list[str] = []
        substitute_failures: list[ProviderDegradation] = []
        for capability in decision.capabilities:
            slot = registry.get(capability)
            name = slot.fallback if slot is not None else None
            if name is None or name in substitutes:
                continue
            if name in collected:
                substitutes.append(name)
                continue
            if name in attempted:
                continue  # tried earlier in this run and failed too
            error = _attempt(
                name,
                physical,
                fingerprint,
                collected=collected,
                attempted=attempted,
                failures=failures,
            )
            if error is None:
                substitutes.append(name)
            else:
                substitute_failures.append(_degradation(name, decision.capabilities, (), error))
        degradations.append(
            _degradation(decision.provider, decision.capabilities, tuple(substitutes), failure)
        )
        # A failing substitute is its own failure, reported after the
        # provider it was standing in for. Substitution never recurses.
        degradations.extend(substitute_failures)
    return ProviderCollection(tuple(collected.values()), tuple(degradations))
