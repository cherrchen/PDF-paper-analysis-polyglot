# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false
"""Unit tests for the local workspace manifest (M8 batch A).

Covers the commit protocol guarantees: the manifest is the single commit
pointer, a COMPLETED stage is trusted only while its artifacts verify and
its input fingerprint still matches upstream records, and unknown manifest
versions or foreign source PDFs are rejected instead of silently migrated.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from pdf_pipeline.workspace import (
    MANIFEST_NAME,
    STAGE_DEPENDENCIES,
    STAGE_ORDER,
    STAGING_DIR,
    WORKSPACE_VERSION,
    Stage,
    StageStatus,
    WorkspaceError,
    WorkspaceManager,
    WorkspaceSourceMismatchError,
    WorkspaceVersionError,
    input_fingerprint,
    sha256_bytes,
)

SOURCE = b"fake source pdf bytes"


def _open(tmp_path: Path, source: bytes = SOURCE) -> WorkspaceManager:
    workspace = WorkspaceManager(tmp_path)
    workspace.open_or_create(source)
    return workspace


def test_stage_order_matches_m8_enum() -> None:
    assert [stage.value for stage in STAGE_ORDER] == [
        "ingest",
        "physical",
        "evidence",
        "layout",
        "semantic",
        "translate",
        "render",
        "index",
    ]


def test_open_creates_manifest(tmp_path: Path) -> None:
    _open(tmp_path)
    payload = json.loads((tmp_path / MANIFEST_NAME).read_text())
    assert payload["workspaceVersion"] == WORKSPACE_VERSION
    assert payload["sourceFingerprint"] == sha256_bytes(SOURCE)
    assert payload["stages"] == {}


def test_unknown_workspace_version_rejected(tmp_path: Path) -> None:
    (tmp_path / MANIFEST_NAME).write_text(json.dumps({"workspaceVersion": "0.0.9"}))
    with pytest.raises(WorkspaceVersionError):
        _open(tmp_path)


def test_corrupt_manifest_rejected(tmp_path: Path) -> None:
    (tmp_path / MANIFEST_NAME).write_text("{not json")
    with pytest.raises(WorkspaceError):
        _open(tmp_path)


def test_foreign_source_rejected(tmp_path: Path) -> None:
    _open(tmp_path)
    with pytest.raises(WorkspaceSourceMismatchError):
        _open(tmp_path, source=b"different pdf bytes")


def test_commit_stage_round_trip(tmp_path: Path) -> None:
    workspace = _open(tmp_path)
    producer = "test-producer"
    fingerprint = input_fingerprint(producer, {})
    workspace.commit_stage(
        Stage.INGEST,
        producer_version=producer,
        input_fingerprint=fingerprint,
        artifacts={"source.pdf": SOURCE},
    )
    reloaded = _open(tmp_path)
    record = reloaded.stage_record(Stage.INGEST)
    assert record is not None
    assert record.status is StageStatus.COMPLETED
    assert record.producer_version == producer
    assert record.input_fingerprint == fingerprint
    assert record.artifacts == {"source.pdf": sha256_bytes(SOURCE)}
    assert reloaded.stage_completed(Stage.INGEST)


def test_stage_completed_detects_tampered_artifact(tmp_path: Path) -> None:
    workspace = _open(tmp_path)
    workspace.commit_stage(
        Stage.INGEST,
        producer_version="test-producer",
        input_fingerprint=input_fingerprint("test-producer", {}),
        artifacts={"source.pdf": SOURCE},
    )
    (tmp_path / "source.pdf").write_bytes(b"tampered")
    assert not workspace.stage_completed(Stage.INGEST)


def test_stage_completed_detects_stale_upstream(tmp_path: Path) -> None:
    workspace = _open(tmp_path)
    producer = "test-producer"
    workspace.commit_stage(
        Stage.INGEST,
        producer_version=producer,
        input_fingerprint=input_fingerprint(producer, {}),
        artifacts={"source.pdf": SOURCE},
    )
    upstream_hashes = {"source.pdf": sha256_bytes(SOURCE)}
    workspace.commit_stage(
        Stage.PHYSICAL,
        producer_version=producer,
        input_fingerprint=input_fingerprint(producer, upstream_hashes),
        artifacts={"physical.json": b"{}"},
    )
    assert workspace.stage_completed(Stage.PHYSICAL)

    # Re-commit INGEST with new bytes: PHYSICAL's recorded fingerprint no
    # longer matches the upstream records, so it must rerun.
    new_source = b"updated source"
    workspace.commit_stage(
        Stage.INGEST,
        producer_version=producer,
        input_fingerprint=input_fingerprint(producer, {}),
        artifacts={"source.pdf": new_source},
    )
    assert not workspace.stage_completed(Stage.PHYSICAL)
    assert workspace.stage_completed(Stage.INGEST)


def test_commit_failure_keeps_manifest_unchanged(tmp_path: Path) -> None:
    workspace = _open(tmp_path)
    # A non-empty directory at an artifact target makes the second replace
    # fail mid-commit, the filesystem-level stand-in for a crash.
    blocked = tmp_path / "resources"
    blocked.mkdir()
    (blocked / "keep.txt").write_bytes(b"old")

    with pytest.raises(OSError, match="Is a directory"):
        workspace.commit_stage(
            Stage.PHYSICAL,
            producer_version="test-producer",
            input_fingerprint=input_fingerprint("test-producer", {}),
            artifacts={"physical.json": b"{}", "resources": b"new"},
        )

    assert workspace.stage_record(Stage.PHYSICAL) is None
    on_disk = json.loads((tmp_path / MANIFEST_NAME).read_text())
    assert "physical" not in on_disk["stages"]
    assert not (tmp_path / STAGING_DIR).exists()
    # Next run does not treat the half-written set as success.
    assert not workspace.stage_completed(Stage.PHYSICAL)


def test_input_fingerprint_is_order_stable() -> None:
    a = input_fingerprint("1.0.0", {"b.json": "hash-b", "a.json": "hash-a"})
    b = input_fingerprint("1.0.0", {"a.json": "hash-a", "b.json": "hash-b"})
    assert a == b
    assert a != input_fingerprint("1.1.0", {"a.json": "hash-a", "b.json": "hash-b"})
    assert a != input_fingerprint("1.0.0", {"a.json": "hash-a"})


def test_stage_dependencies_cover_every_stage() -> None:
    assert set(STAGE_DEPENDENCIES) == set(STAGE_ORDER)
    for stage, deps in STAGE_DEPENDENCIES.items():
        index = STAGE_ORDER.index(stage)
        assert all(STAGE_ORDER.index(dep) < index for dep in deps)


def test_manifest_write_failure_restores_memory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = _open(tmp_path)

    def fail() -> None:
        raise OSError("manifest write failed")

    monkeypatch.setattr(workspace, "_write_manifest", fail)
    with pytest.raises(OSError, match="manifest write failed"):
        workspace.commit_stage(
            Stage.INGEST,
            producer_version="1",
            input_fingerprint=input_fingerprint("1", {}),
            artifacts={"source.pdf": SOURCE},
        )
    assert workspace.stage_record(Stage.INGEST) is None
    assert not workspace.stage_completed(Stage.INGEST)


@pytest.mark.parametrize("status", [[], {}])
def test_invalid_status_is_workspace_error(tmp_path: Path, status: object) -> None:
    workspace = _open(tmp_path)
    payload = json.loads(workspace.manifest_path.read_text())
    payload["stages"] = {"ingest": {"status": status}}
    workspace.manifest_path.write_text(json.dumps(payload))
    with pytest.raises(WorkspaceError):
        _open(tmp_path)


@pytest.mark.parametrize(
    "name", ["../escape", "/outside/escape", "workspace.json", ".staging/x", "."]
)
def test_artifact_paths_cannot_escape_or_replace_manifest(tmp_path: Path, name: str) -> None:
    workspace = _open(tmp_path)
    before = workspace.manifest_path.read_bytes()
    with pytest.raises(WorkspaceError):
        workspace.commit_stage(
            Stage.INGEST,
            producer_version="1",
            input_fingerprint=input_fingerprint("1", {}),
            artifacts={name: b"invalid"},
        )
    assert workspace.manifest_path.read_bytes() == before
