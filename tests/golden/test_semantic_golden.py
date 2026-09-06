"""Golden regression for the semantic recovery engine.

Expected canonical SemanticDocument for the ``smoke`` fixture lives at
``tests/golden/smoke/semantic.json``. Comparison remaps opaque IDs that
are derived from PDF bytes: ``just latex-smoke`` PDFs are not
byte-identical across TeX installs, so UUID equality is not the contract.
Kinds, text, tree shape, and non-id attributes are. PDFium whitespace is
normalized. Never regenerate golden output merely to make this pass
(docs/testing/golden.md).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest
from document_model import dump_document
from pdf_pipeline.layout import recover_layout_document
from pdf_pipeline.physical import extract_physical_document
from pdf_pipeline.pipeline import region_lines_from, region_texts_from
from pdf_pipeline.semantic import recover_semantic_document

if TYPE_CHECKING:
    from document_model.generated.schema_models import SemanticDocument

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests/fixtures/source/latex/build"
GOLDEN = ROOT / "tests/golden"

_SCALAR_ID_KEYS = frozenset(
    {
        "id",
        "rootId",
        "layoutDocumentId",
        "parentId",
        "source",
        "target",
        "targetNodeId",
    }
)
# Region-id lists (multi-fragment anchors) canonicalize element-wise.
_LIST_ID_KEYS = frozenset({"children", "provenanceIds", "layoutRegionIds"})


def _canonicalize_semantic(payload: object) -> object:
    """Rewrite fingerprint-derived IDs to encounter-order placeholders."""
    mapping: dict[str, str] = {}

    def assign(raw: str) -> str:
        mapped = mapping.get(raw)
        if mapped is None:
            mapped = f"id-{len(mapping):04d}"
            mapping[raw] = mapped
        return mapped

    def walk(value: object, key: str | None = None) -> object:
        if isinstance(value, dict):
            items = cast("dict[str, object]", value)
            return {item_key: walk(item, item_key) for item_key, item in items.items()}
        if isinstance(value, list):
            entries = cast("list[object]", value)
            if key in _LIST_ID_KEYS:
                return [assign(item) if isinstance(item, str) else walk(item) for item in entries]
            return [walk(item) for item in entries]
        if isinstance(value, str):
            if key in _SCALAR_ID_KEYS:
                return assign(value)
            if key in {"text", "rawText", "unicodeText"}:
                return " ".join(value.replace("\r", " ").split())
        return value

    return walk(payload)


def _fixture_pdf(fixture: str) -> Path:
    path = FIXTURES / f"{fixture}.pdf"
    if not path.exists():
        pytest.skip(f"fixture PDF {fixture} not built; run `just latex-smoke`")
    return path


def _expected_semantic(fixture: str) -> SemanticDocument:
    physical = extract_physical_document(_fixture_pdf(fixture).read_bytes())
    layout = recover_layout_document(physical)
    return recover_semantic_document(
        layout,
        region_texts_from(physical, layout),
        lines=region_lines_from(physical, layout),
    )


def test_canonicalize_semantic_remaps_opaque_ids() -> None:
    left: dict[str, object] = {
        "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "rootId": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        "nodes": [
            {
                "id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                "kind": "DOCUMENT",
                "parentId": None,
                "children": ["cccccccc-cccc-cccc-cccc-cccccccccccc"],
                "content": {"text": "root", "marks": cast("list[object]", [])},
            }
        ],
    }
    right: dict[str, object] = {
        "id": "11111111-1111-1111-1111-111111111111",
        "rootId": "22222222-2222-2222-2222-222222222222",
        "nodes": [
            {
                "id": "22222222-2222-2222-2222-222222222222",
                "kind": "DOCUMENT",
                "parentId": None,
                "children": ["33333333-3333-3333-3333-333333333333"],
                "content": {"text": "root", "marks": cast("list[object]", [])},
            }
        ],
    }
    assert _canonicalize_semantic(left) == _canonicalize_semantic(right)


@pytest.mark.golden
@pytest.mark.parametrize("fixture", ["smoke"])
def test_golden_semantic_document(fixture: str) -> None:
    golden_path = GOLDEN / fixture / "semantic.json"
    if not golden_path.exists():
        pytest.skip(f"golden baseline missing for {fixture}")
    expected = json.loads(golden_path.read_text(encoding="utf-8"))
    actual = dump_document(_expected_semantic(fixture))
    assert _canonicalize_semantic(actual) == _canonicalize_semantic(expected)
