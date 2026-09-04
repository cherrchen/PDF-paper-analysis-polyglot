"""Cross-language roundtrip: Python serialize -> JSON -> TS -> Python.

Phase 1.7 validation. Requires ``node`` on PATH; the TS side reads the
canonical JSON Schemas directly, so a pass means both language bindings
agree with the same contract.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
from document_model import dump_document, load_document

ROOT = Path(__file__).resolve().parents[2]
ROUNDTRIP = ROOT / "packages/typescript/document-model/roundtrip.mjs"

CASES = [
    ("physical-document", "two-page-two-column.valid.json"),
    ("evidence", "mock-providers.valid.json"),
    ("layout-document", "two-column-spanning-figure.valid.json"),
    ("semantic-document", "paper-structure.valid.json"),
    ("mapping", "three-binding-scenarios.valid.json"),
]


def _fixture(schema_dir: str, name: str) -> dict[str, Any]:
    text = (ROOT / "schemas/fixtures" / schema_dir / name).read_text(encoding="utf-8")
    data: dict[str, Any] = json.loads(text)
    return data


@pytest.mark.integration
@pytest.mark.parametrize(("schema_dir", "fixture_name"), CASES)
def test_python_node_python_roundtrip(tmp_path: Path, schema_dir: str, fixture_name: str) -> None:
    data = _fixture(schema_dir, fixture_name)

    # Python serialize
    doc = load_document(schema_dir, data)
    first = dump_document(doc)
    assert first == data

    src = tmp_path / "in.json"
    dst = tmp_path / "out.json"
    src.write_text(json.dumps(first), encoding="utf-8")

    # TS validate and re-serialize
    result = subprocess.run(  # noqa: S603 - node resolves from PATH, fixed inputs
        ["node", str(ROUNDTRIP), schema_dir, str(src), str(dst)],  # noqa: S607
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=False,
    )
    assert result.returncode == 0, f"TS validation failed: {result.stderr}"

    # Python deserialize the TS output
    ts_output = json.loads(dst.read_text(encoding="utf-8"))
    restored = load_document(schema_dir, ts_output)
    assert dump_document(restored) == data, "roundtrip must be semantically identical"


@pytest.mark.integration
def test_ts_rejects_invalid_document(tmp_path: Path) -> None:
    data = _fixture("semantic-document", "paper-structure.valid.json")
    data["nodes"][0]["bbox"] = [0, 0, 1, 1]  # geometry must never enter semantic layer
    src = tmp_path / "bad.json"
    src.write_text(json.dumps(data), encoding="utf-8")
    result = subprocess.run(  # noqa: S603 - node resolves from PATH, fixed inputs
        ["node", str(ROUNDTRIP), "semantic-document", str(src)],  # noqa: S607
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=False,
    )
    assert result.returncode == 1
    assert "bbox" in result.stderr or "additional" in result.stderr
