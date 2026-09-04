"""Golden regression for the M2 Walking Skeleton.

Expected canonical SemanticDocument for the ``smoke`` fixture lives at
``tests/golden/smoke/semantic.json``. Comparison normalizes nothing that is
not already deterministic: extraction, recovery, and translation all derive
IDs and content from source bytes, so byte equality after JSON parsing is
the contract. Never regenerate golden output merely to make this pass
(docs/testing/golden.md).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from document_model import dump_document
from paper_llm import translate_document
from pdf_pipeline.layout import recover_layout_document
from pdf_pipeline.physical import extract_physical_document
from pdf_pipeline.pipeline import region_texts_from
from pdf_pipeline.semantic import recover_semantic_document

if TYPE_CHECKING:
    from document_model.generated import SemanticDocument

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests/fixtures/source/latex/build"
GOLDEN = ROOT / "tests/golden"


def _expected_semantic(fixture: str) -> SemanticDocument:
    physical = extract_physical_document((FIXTURES / f"{fixture}.pdf").read_bytes())
    layout = recover_layout_document(physical)
    semantic = recover_semantic_document(layout, region_texts_from(physical, layout))
    return translate_document(semantic)


@pytest.mark.golden
@pytest.mark.parametrize("fixture", ["smoke"])
def test_golden_semantic_document(fixture: str) -> None:
    golden_path = GOLDEN / fixture / "semantic.json"
    if not golden_path.exists():
        pytest.skip(f"golden baseline missing for {fixture}")
    expected = json.loads(golden_path.read_text(encoding="utf-8"))
    actual = dump_document(_expected_semantic(fixture))
    assert actual == expected
