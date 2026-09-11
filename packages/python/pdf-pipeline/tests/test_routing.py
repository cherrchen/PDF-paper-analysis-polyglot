"""Phase 7.3 Adaptive Routing tests: probe -> deterministic provider plan.

The plan must select providers per the Capability Registry, wake the
table specialist only for table-dense documents, tag formula capability
for math-heavy documents, and refuse textless documents.
"""

from __future__ import annotations

import pytest
from document_model import dump_document, load_document
from pdf_pipeline.capabilities import load_registry
from pdf_pipeline.evidence.normalize import merge_evidence_bundles
from pdf_pipeline.probe import ProbeResult
from pdf_pipeline.routing import build_provider, collect_bundles, route_providers


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
    bundles = collect_bundles(plan, physical)
    assert len(bundles) == len(plan.provider_names())
    merged = merge_evidence_bundles(bundles)
    assert merged.provider.startswith("ensemble:")
    assert merged.candidates
    load_document("evidence", dump_document(merged))
