"""Phase 7.3 Adaptive Routing tests: probe -> deterministic provider plan.

The plan must select providers per the Capability Registry, wake the
table specialist only for table-dense documents, tag formula capability
for math-heavy documents, and refuse textless documents.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from document_model import dump_document, load_document
from pdf_pipeline.capabilities import Capability, load_registry
from pdf_pipeline.evidence.normalize import merge_evidence_bundles
from pdf_pipeline.probe import ProbeResult
from pdf_pipeline.routing import build_provider, collect_bundles, route_providers

if TYPE_CHECKING:
    from pathlib import Path


def _probe(
    *,
    native: float = 1.0,
    table: float = 0.0,
    math: float = 0.0,
    columns: int | None = 1,
) -> ProbeResult:
    return ProbeResult(
        native_text_ratio=native,
        scanned_page_ratio=1.0 - native,
        math_density=math,
        table_density=table,
        image_density=0.0,
        estimated_columns=columns,
        layout_complexity=0.2,
    )


def test_plain_paper_routes_layout_and_scholarly() -> None:
    plan = route_providers(_probe())
    assert plan.provider_names() == ("mock", "grobid-sim")
    assert plan.decisions[0].capabilities == ("layout.region",)
    assert plan.decisions[1].capabilities == ("scholarly.metadata", "scholarly.bibliography")


def test_table_dense_paper_wakes_table_specialist() -> None:
    plan = route_providers(_probe(table=0.5))
    assert plan.provider_names() == ("mock", "docling-sim", "grobid-sim")
    table_decision = plan.decisions[1]
    assert table_decision.capabilities == ("table.structure", "table.detection")
    assert "table density" in table_decision.reason


def test_math_heavy_paper_tags_formula_capability() -> None:
    plan = route_providers(_probe(math=0.2))
    assert plan.decisions[0].capabilities == ("layout.region", "formula.detection")
    assert "math density" in plan.decisions[0].reason


def test_routing_plan_is_deterministic() -> None:
    probe = _probe(table=0.4, math=0.1, columns=2)
    assert route_providers(probe).to_json() == route_providers(probe).to_json()


def test_textless_document_is_refused() -> None:
    with pytest.raises(ValueError, match="text layer"):
        route_providers(_probe(native=0.0))


def test_registry_names_drive_selection() -> None:
    registry = load_registry()
    plan = route_providers(_probe(table=1.0), registry)
    assert plan.provider_names() == (
        registry["layout.region"].primary,
        registry["table.structure"].primary,
        registry["scholarly.metadata"].primary,
    )


def test_build_provider_covers_all_routed_names() -> None:
    plan = route_providers(_probe(table=1.0))
    providers = [build_provider(name) for name in plan.provider_names()]
    assert all(hasattr(provider, "collect") for provider in providers)
    with pytest.raises(KeyError, match="no provider implementation"):
        build_provider("nonexistent")


def test_collect_bundles_produce_schema_valid_evidence() -> None:
    from test_fake_specialists import table_page

    physical = table_page()
    plan = route_providers(_probe(table=1.0))
    collection = collect_bundles(plan, physical)
    assert collection.degradations == ()
    assert not collection.degraded
    assert len(collection.bundles) == len(plan.provider_names())
    merged = merge_evidence_bundles(collection.bundles)
    assert merged.provider.startswith("ensemble:")
    assert merged.candidates
    assert merged.issues is None
    load_document("evidence", dump_document(merged))


# --- Provider failure isolation (M8 batch D) ------------------------------


def _registry_with(
    capability: str,
    *,
    primary: str | None = None,
    fallback: str | None = None,
) -> dict[str, Capability]:
    """Overlay one capability slot on top of the bundled registry."""
    overlay = dict(load_registry())
    slot = overlay[capability]
    overlay[capability] = Capability(
        name=slot.name,
        primary=primary if primary is not None else slot.primary,
        challenger=slot.challenger,
        fallback=fallback if fallback is not None else slot.fallback,
    )
    return overlay


def test_failed_table_specialist_substitutes_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A dead Docling dump degrades the table capability, not the run."""
    from test_fake_specialists import table_page

    monkeypatch.setenv("DOCLING_DUMP", str(tmp_path / "missing.json"))
    physical = table_page()
    registry = _registry_with("table.structure", primary="docling", fallback="mock")
    plan = route_providers(_probe(table=1.0), registry)
    collection = collect_bundles(plan, physical, registry)

    assert [bundle.provider for bundle in collection.bundles] == ["mock", "grobid-sim"]
    (degradation,) = collection.degradations
    assert (
        degradation.provider,
        degradation.capabilities,
        degradation.substitutes,
        degradation.errorType,
    ) == ("docling", ("table.structure", "table.detection"), ("mock",), "FileNotFoundError")
    payload = degradation.to_json()
    assert payload["category"] == "TABLE_RECOVERY"
    assert payload["substitutes"] == ["mock"]

    issue = degradation.to_issue(physical.id)
    assert (issue.category, issue.severity, issue.producer, issue.recoverable) == (
        "TABLE_RECOVERY",
        "ERROR",
        "docling",
        True,
    )
    assert issue.fallback == "provider substitution: mock"
    assert issue.affectedIds == []

    merged = merge_evidence_bundles(collection.bundles, issues=collection.issues(physical.id))
    assert merged.issues is not None
    assert [issue.producer for issue in merged.issues.issues] == ["docling"]
    load_document("evidence", dump_document(merged))


def test_failed_metadata_specialist_without_fallback_continues(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No registry fallback: the internal baseline covers the capability."""
    from test_fake_specialists import table_page

    monkeypatch.setenv("GROBID_DUMP", str(tmp_path / "missing.json"))
    physical = table_page()
    registry = _registry_with("scholarly.metadata", primary="grobid")
    plan = route_providers(_probe(), registry)
    collection = collect_bundles(plan, physical, registry)

    assert [bundle.provider for bundle in collection.bundles] == ["mock"]
    (degradation,) = collection.degradations
    assert degradation.provider == "grobid"
    assert degradation.capabilities == ("scholarly.metadata", "scholarly.bibliography")
    assert degradation.substitutes == ()
    issue = degradation.to_issue(physical.id)
    assert issue.category == "SECTION_STRUCTURE"
    assert issue.fallback == "front-matter heuristics"


def test_failing_substitute_is_recorded_separately(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Substitution is one level deep: a dead substitute is its own failure."""
    from test_fake_specialists import table_page

    monkeypatch.setenv("DOCLING_DUMP", str(tmp_path / "missing-docling.json"))
    monkeypatch.setenv("MINERU_DUMP", str(tmp_path / "missing-mineru.json"))
    physical = table_page()
    registry = _registry_with("table.structure", primary="docling", fallback="mineru")
    plan = route_providers(_probe(table=1.0), registry)
    collection = collect_bundles(plan, physical, registry)

    assert [degradation.provider for degradation in collection.degradations] == [
        "docling",
        "mineru",
    ]
    docling, mineru = collection.degradations
    assert docling.substitutes == ()
    assert mineru.capabilities == ("table.structure", "table.detection")
    assert mineru.substitutes == ()
    assert [bundle.provider for bundle in collection.bundles] == ["mock", "grobid-sim"]


def test_layout_primary_failure_keeps_geometric_regions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without the layout provider the geometric baseline still yields regions."""
    from pdf_pipeline.layout import recover_layout_document
    from pdf_pipeline.pipeline import region_texts_from
    from test_fake_specialists import table_page

    monkeypatch.setenv("MINERU_DUMP", str(tmp_path / "missing.json"))
    physical = table_page()
    registry = _registry_with("layout.region", primary="mineru")
    plan = route_providers(_probe(), registry)
    collection = collect_bundles(plan, physical, registry)

    assert [bundle.provider for bundle in collection.bundles] == ["grobid-sim"]
    (degradation,) = collection.degradations
    assert degradation.to_json()["category"] == "LAYOUT_REGION"

    layout = recover_layout_document(physical, evidence=collection.bundles, registry=registry)
    assert layout.regions
    assert any(text for text in region_texts_from(physical, layout).values())
