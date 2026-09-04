"""Layer responsibility boundary tests (M1 exit gate requirement)."""

from __future__ import annotations

from typing import Any

import pytest
from document_model import validate_layer_separation


@pytest.mark.unit
def test_clean_bundle_has_no_violations(
    layout_data: dict[str, Any], semantic_data: dict[str, Any]
) -> None:
    assert validate_layer_separation(layout_data, semantic_data) == []


@pytest.mark.unit
def test_semantic_node_with_bbox_is_flagged(
    layout_data: dict[str, Any], semantic_data: dict[str, Any]
) -> None:
    polluted: dict[str, Any] = {
        **semantic_data,
        "nodes": [
            *semantic_data["nodes"],
            {
                "id": "01J5M1FXTRES0AAAAAAA0BBOX1",
                "kind": "PARAGRAPH",
                "children": [],
                "content": {"text": "x", "marks": []},
                "attributes": {"bbox": [0, 0, 10, 10]},
                "confidence": {"score": 1.0},
                "provenanceIds": [],
            },
        ],
    }
    issues = validate_layer_separation(layout_data, polluted)
    assert any("bbox" in issue for issue in issues)


@pytest.mark.unit
def test_semantic_node_with_page_is_flagged(
    layout_data: dict[str, Any], semantic_data: dict[str, Any]
) -> None:
    polluted: dict[str, Any] = dict(semantic_data)
    polluted["nodes"] = [
        {**node, "page": 3} if node["kind"] == "PARAGRAPH" else node
        for node in semantic_data["nodes"]
    ]
    issues = validate_layer_separation(layout_data, polluted)
    assert any("page" in issue for issue in issues)


@pytest.mark.unit
def test_layout_region_with_semantic_label_is_flagged(
    layout_data: dict[str, Any], semantic_data: dict[str, Any]
) -> None:
    polluted: dict[str, Any] = dict(layout_data)
    polluted["regions"] = [
        {**region, "method_section": True} if region["kind"] == "TEXT" else region
        for region in layout_data["regions"]
    ]
    issues = validate_layer_separation(polluted, semantic_data)
    assert any("method_section" in issue for issue in issues)


@pytest.mark.unit
def test_semantic_label_in_layout_labels_is_flagged(
    layout_data: dict[str, Any], semantic_data: dict[str, Any]
) -> None:
    polluted: dict[str, Any] = dict(layout_data)
    polluted["regions"] = [
        {
            **region,
            "labels": [
                {"label": "SECTION", "confidence": 0.9, "evidenceIds": []},
                *region.get("labels", []),
            ],
        }
        for region in layout_data["regions"]
    ]
    issues = validate_layer_separation(polluted, semantic_data)
    assert any("SECTION" in issue for issue in issues)
