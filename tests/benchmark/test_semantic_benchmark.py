"""M4 semantic benchmark: recovered semantics vs hand-derived ground truth.

Ground truth lives in ``tests/fixtures/layout-truth/<fixture>.json`` under
the ``semantic`` key, derived from each fixture's LaTeX source plus the
M3/M4 measurements. The M4 exit gate becomes mechanical here: required
kinds, per-kind minimums, relation counts (CAPTION_OF / FOOTNOTE_OF /
CITES), inline-mark minimums, equation numbers, heading levels, merged
multi-region nodes, table cells, multi-fragment anchors, semantic
coverage, and zero ERROR issues from the semantic validator. Every
fixture additionally round-trips the full bundle-reference contract.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from document_model import dump_document, validate_bundle_references
from document_model.generated import schema_models as generated
from pdf_pipeline.evidence.providers import MockLayoutEvidenceProvider
from pdf_pipeline.layout import recover_layout_document
from pdf_pipeline.physical import extract_physical_document
from pdf_pipeline.pipeline import (
    build_source_anchors,
    region_lines_from,
    region_texts_from,
)
from pdf_pipeline.render_anchor import build_mapping_bundle
from pdf_pipeline.sem_validate import validate_semantic_recovery
from pdf_pipeline.semantic import recover_semantic_document

if TYPE_CHECKING:
    from document_model.generated.schema_models import (
        LayoutDocument,
        PhysicalDocument,
        SemanticDocument,
    )

ROOT = Path(__file__).resolve().parents[2]
BUILD_DIR = ROOT / "tests/fixtures/source/latex/build"
TRUTH_DIR = ROOT / "tests/fixtures/layout-truth"


def _truths() -> list[tuple[str, dict[str, Any]]]:
    cases: list[tuple[str, dict[str, Any]]] = []
    for path in sorted(TRUTH_DIR.glob("*.json")):
        truth = json.loads(path.read_text())
        if "semantic" in truth:
            cases.append((truth["fixture"], truth["semantic"]))
    return cases


TRUTHS = _truths()


def _recover(
    fixture: str,
) -> tuple[PhysicalDocument, LayoutDocument, SemanticDocument, dict[str, str]]:
    pdf_path = BUILD_DIR / f"{fixture}.pdf"
    if not pdf_path.exists():
        pytest.skip(f"fixture PDF {fixture} not built; run `just latex-smoke`")
    physical = extract_physical_document(pdf_path.read_bytes())
    evidence = MockLayoutEvidenceProvider().collect(physical)
    layout = recover_layout_document(physical, evidence=evidence)
    texts = region_texts_from(physical, layout)
    semantic = recover_semantic_document(
        layout, texts, lines=region_lines_from(physical, layout), evidence=evidence
    )
    return physical, layout, semantic, texts


def _mark_counts(semantic: SemanticDocument) -> Counter[str]:
    return Counter(
        mark.type
        for node in semantic.nodes
        if isinstance(node.content, generated.RichText)
        for mark in node.content.marks
    )


def _heading_levels(semantic: SemanticDocument) -> list[int]:
    return sorted(
        {
            node.attributes["level"]
            for node in semantic.nodes
            if node.kind == "HEADING" and isinstance(node.attributes.get("level"), int)
        }
    )


def _equation_numbers(semantic: SemanticDocument) -> list[str]:
    return sorted(
        node.content.number
        for node in semantic.nodes
        if isinstance(node.content, generated.EquationContent) and node.content.number
    )


def _merged_nodes(semantic: SemanticDocument) -> int:
    return sum(
        1
        for node in semantic.nodes
        if node.kind in {"PARAGRAPH", "BIBLIOGRAPHY_ENTRY", "EQUATION"}
        and len(node.attributes.get("layoutRegionIds", [])) > 1
    )


def _table_cells(semantic: SemanticDocument) -> int:
    return sum(
        len(node.content.cells)
        for node in semantic.nodes
        if isinstance(node.content, generated.TableContent)
    )


def _coverage(layout: LayoutDocument, texts: dict[str, str], semantic: SemanticDocument) -> float:
    bound = {
        region_id
        for node in semantic.nodes
        for region_id in node.attributes.get("layoutRegionIds", [])
    }
    primary = set(layout.primaryFlow)
    required = {
        region.id
        for region in layout.regions
        if region.id in primary
        and region.kind in {"TEXT", "TABLE", "FORMULA"}
        and texts.get(region.id, "").strip()
    }
    return len(required & bound) / len(required) if required else 1.0


@pytest.mark.parametrize(("fixture", "expectation"), TRUTHS, ids=[fixture for fixture, _ in TRUTHS])
def test_semantic_benchmark(fixture: str, expectation: dict[str, Any]) -> None:
    _physical, layout, semantic, texts = _recover(fixture)

    kinds = {node.kind for node in semantic.nodes}
    assert set(expectation["kinds"]) <= kinds, (
        f"{fixture}: missing kinds {set(expectation['kinds']) - kinds}"
    )

    counts = Counter(node.kind for node in semantic.nodes)
    for kind, minimum in expectation["minCounts"].items():
        assert counts[kind] >= minimum, f"{fixture}: {kind} {counts[kind]} < {minimum}"

    relations = Counter(relation.type for relation in semantic.relations)
    for kind, expected in (
        ("CAPTION_OF", expectation["captionOf"]),
        ("FOOTNOTE_OF", expectation["footnotesLinked"]),
        ("CITES", expectation["citationsResolved"]),
    ):
        assert relations[kind] == expected, f"{fixture}: {kind} {relations[kind]} != {expected}"

    marks = _mark_counts(semantic)
    for kind, minimum in expectation["marks"].items():
        assert marks[kind] >= minimum, f"{fixture}: mark {kind} {marks[kind]} < {minimum}"

    assert _equation_numbers(semantic) == sorted(expectation["equationNumbers"]), fixture
    assert _heading_levels(semantic) == sorted(expectation["headingLevels"]), fixture
    assert _merged_nodes(semantic) >= expectation["mergedParagraphNodes"], fixture
    assert _table_cells(semantic) >= expectation.get("tableCellsMin", 0), fixture

    if "frontMatterRoles" in expectation:
        roles = {
            node.attributes.get("role")
            for node in semantic.nodes
            if isinstance(node.attributes.get("role"), str)
        }
        missing = set(expectation["frontMatterRoles"]) - roles
        assert not missing, f"{fixture}: missing front-matter roles {missing}"

    if "sectionParentOf" in expectation:
        sections = {
            node.attributes["numbering"]: node
            for node in semantic.nodes
            if node.kind == "SECTION" and isinstance(node.attributes.get("numbering"), str)
        }
        for child_number, parent_number in expectation["sectionParentOf"].items():
            assert sections[child_number].parentId == sections[parent_number].id, (
                f"{fixture}: section {child_number} parent is not {parent_number}"
            )

    if "figureLabels" in expectation:
        labels = sorted(
            node.content.label
            for node in semantic.nodes
            if isinstance(node.content, generated.FigureContent) and node.content.label
        )
        assert labels == sorted(expectation["figureLabels"]), fixture

    ratio = _coverage(layout, texts, semantic)
    assert ratio >= expectation["coverageMin"], f"{fixture}: coverage {ratio:.2f}"

    issues = validate_semantic_recovery(semantic, layout, texts)
    if expectation["noErrors"]:
        errors = [issue.message for issue in issues if issue.severity in ("ERROR", "FATAL")]
        assert not errors, f"{fixture}: {errors}"
    assert not [issue for issue in issues if issue.category == "SOURCE_MAPPING"], (
        f"{fixture}: mapping issues {[i.message for i in issues]}"
    )


@pytest.mark.parametrize(("fixture", "expectation"), TRUTHS, ids=[fixture for fixture, _ in TRUTHS])
def test_semantic_bundle_and_anchors(fixture: str, expectation: dict[str, Any]) -> None:
    physical, layout, semantic, _texts = _recover(fixture)
    _plb, anchors, ssb = build_source_anchors(physical, layout, semantic)
    multi = sum(1 for anchor in anchors if len(anchor.fragments) > 1)
    assert multi >= expectation["multiFragmentAnchors"], (
        f"{fixture}: multi-fragment anchors {multi} < {expectation['multiFragmentAnchors']}"
    )

    # M6 DoD "Validation metrics available": every body node kind that the
    # reader must navigate to is actually bound in sourceSemanticBindings.
    bound_nodes = {binding.semanticNodeId for binding in ssb}
    navigable = [
        node for node in semantic.nodes if node.kind in {"HEADING", "PARAGRAPH", "FIGURE_CAPTION"}
    ]
    covered = [node for node in navigable if node.id in bound_nodes]
    anchor_coverage = len(covered) / len(navigable) if navigable else 1.0
    assert anchor_coverage >= 0.8, (
        f"{fixture}: anchorCoverage {anchor_coverage:.2f} ({len(covered)}/{len(navigable)}) < 0.8"
    )

    mapping = build_mapping_bundle(
        semantic,
        source_anchors=anchors,
        source_semantic_bindings=ssb,
        physical_layout_bindings=_bindings(layout),
        render_anchors=[],
        render_document_id="00000000-0000-0000-0000-000000000000",
    )
    bundle = {
        "physical": dump_document(physical),
        "layout": dump_document(layout),
        "semantic": dump_document(semantic),
        "mappings": dump_document(mapping),
    }
    assert validate_bundle_references(bundle) == []


def _bindings(layout: LayoutDocument) -> list[generated.PhysicalLayoutBinding]:
    from pdf_pipeline.ids import stable_uuid

    return [
        generated.PhysicalLayoutBinding(
            id=stable_uuid(layout.id, "plb", region.id),
            layoutRegionId=region.id,
            physicalObjectIds=list(region.physicalObjectIds),
        )
        for region in layout.regions
    ]
