# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false
"""Unit tests for the local workspace manifest (M8 batches A/C).

Covers the commit protocol guarantees: the manifest is the single commit
pointer, a COMPLETED stage is trusted only while its artifacts verify and
its cache key (producer version + upstream artifacts + stage config) still
matches, and unknown manifest versions or foreign source PDFs are rejected
instead of silently migrated — unless a rebinding to new source bytes is
explicitly requested.
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

PRODUCER = "test-producer"


def _open(
    tmp_path: Path,
    source: bytes = SOURCE,
    *,
    stage_configs: dict[Stage, dict[str, str]] | None = None,
    accept_source_change: bool = False,
) -> WorkspaceManager:
    workspace = WorkspaceManager(tmp_path, stage_configs=stage_configs)
    workspace.open_or_create(source, accept_source_change=accept_source_change)
    return workspace


def _commit(workspace: WorkspaceManager, stage: Stage, payload: bytes | None = None) -> None:
    """Commit ``stage`` with one artifact, distinct per stage and payload."""
    workspace.commit_stage(
        stage,
        producer_version=PRODUCER,
        artifacts={f"{stage.value}.json": payload or f"{stage.value} bytes".encode()},
    )


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


def test_supported_workspace_version_loads(tmp_path: Path) -> None:
    (tmp_path / MANIFEST_NAME).write_text(
        json.dumps(
            {
                "workspaceVersion": WORKSPACE_VERSION,
                "sourceFingerprint": sha256_bytes(SOURCE),
                "stages": {},
            }
        )
    )
    workspace = _open(tmp_path)
    assert workspace.stages == {}


def test_unknown_workspace_version_refused_without_touching(tmp_path: Path) -> None:
    (tmp_path / MANIFEST_NAME).write_text(json.dumps({"workspaceVersion": "9.9.9"}))
    before = (tmp_path / MANIFEST_NAME).read_bytes()

    with pytest.raises(WorkspaceVersionError, match=r"9\.9\.9"):
        _open(tmp_path)

    # Refused, not migrated and not partially adopted: no disk write, no
    # staging directory left behind.
    assert (tmp_path / MANIFEST_NAME).read_bytes() == before
    assert not (tmp_path / STAGING_DIR).exists()


def test_manifest_absent_directory_is_not_trusted(tmp_path: Path) -> None:
    """Artifacts without a manifest are a new workspace, not a resumed one."""
    (tmp_path / "semantic.json").write_text(json.dumps({"nodes": []}))

    workspace = _open(tmp_path)

    assert workspace.manifest_path.is_file()
    assert not workspace.stage_completed(Stage.SEMANTIC)


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
    fingerprint = input_fingerprint(PRODUCER, {})
    workspace.commit_stage(
        Stage.INGEST,
        producer_version=PRODUCER,
        artifacts={"source.pdf": SOURCE},
    )
    reloaded = _open(tmp_path)
    record = reloaded.stage_record(Stage.INGEST)
    assert record is not None
    assert record.status is StageStatus.COMPLETED
    assert record.producer_version == PRODUCER
    assert record.input_fingerprint == fingerprint
    assert record.artifacts == {"source.pdf": sha256_bytes(SOURCE)}
    assert reloaded.stage_completed(Stage.INGEST)


def test_degraded_commit_reruns_next_time(tmp_path: Path) -> None:
    workspace = _open(tmp_path)
    workspace.commit_stage(
        Stage.INGEST,
        producer_version=PRODUCER,
        artifacts={"source.pdf": SOURCE},
    )
    workspace.commit_stage(
        Stage.PHYSICAL,
        producer_version=PRODUCER,
        artifacts={"physical.json": b"physical bytes"},
    )
    workspace.commit_stage(
        Stage.EVIDENCE,
        producer_version=PRODUCER,
        artifacts={"evidence.json": b"evidence bytes"},
        degraded=True,
    )

    manifest = json.loads((tmp_path / MANIFEST_NAME).read_text())
    assert manifest["stages"]["evidence"]["status"] == "degraded"
    assert not workspace.stage_completed(Stage.EVIDENCE)

    reloaded = _open(tmp_path)
    record = reloaded.stage_record(Stage.EVIDENCE)
    assert record is not None
    assert record.status is StageStatus.DEGRADED
    assert not reloaded.stage_completed(Stage.EVIDENCE)


def test_stage_completed_detects_tampered_artifact(tmp_path: Path) -> None:
    workspace = _open(tmp_path)
    _commit(workspace, Stage.INGEST, SOURCE)
    (tmp_path / "ingest.json").write_bytes(b"tampered")
    assert not workspace.stage_completed(Stage.INGEST)


def test_stage_completed_detects_stale_upstream(tmp_path: Path) -> None:
    workspace = _open(tmp_path)
    _commit(workspace, Stage.INGEST, SOURCE)
    _commit(workspace, Stage.PHYSICAL)
    assert workspace.stage_completed(Stage.PHYSICAL)

    # Re-commit INGEST with new bytes: PHYSICAL's recorded fingerprint no
    # longer matches the upstream records, so it must rerun.
    _commit(workspace, Stage.INGEST, b"updated source")
    assert not workspace.stage_completed(Stage.PHYSICAL)
    assert workspace.stage_completed(Stage.INGEST)


def test_stage_config_change_invalidates_stage(tmp_path: Path) -> None:
    configs = {Stage.INGEST: {"k": "1"}}
    workspace = _open(tmp_path, stage_configs=configs)
    _commit(workspace, Stage.INGEST)
    assert workspace.stage_completed(Stage.INGEST)

    changed = _open(tmp_path, stage_configs={Stage.INGEST: {"k": "2"}})
    assert not changed.stage_completed(Stage.INGEST)


def test_commit_requires_committed_upstream(tmp_path: Path) -> None:
    workspace = _open(tmp_path)
    with pytest.raises(WorkspaceError, match="upstream stage not committed: ingest"):
        _commit(workspace, Stage.PHYSICAL)


def test_invalidate_from_drops_stage_and_downstream(tmp_path: Path) -> None:
    workspace = _open(tmp_path)
    for stage in STAGE_ORDER[: STAGE_ORDER.index(Stage.SEMANTIC) + 1]:
        _commit(workspace, stage)
    assert workspace.stage_record(Stage.SEMANTIC) is not None

    workspace.invalidate_from(Stage.LAYOUT)

    assert workspace.stage_record(Stage.LAYOUT) is None
    assert workspace.stage_record(Stage.SEMANTIC) is None
    for stage in (Stage.INGEST, Stage.PHYSICAL, Stage.EVIDENCE):
        assert workspace.stage_record(stage) is not None
    # The manifest, not just memory, lost the dropped records.
    on_disk = json.loads((tmp_path / MANIFEST_NAME).read_text())["stages"]
    assert set(on_disk) == {"ingest", "physical", "evidence"}


def test_accept_source_change_rebinds_and_invalidates(tmp_path: Path) -> None:
    workspace = _open(tmp_path)
    _commit(workspace, Stage.INGEST)
    _commit(workspace, Stage.PHYSICAL)

    with pytest.raises(WorkspaceSourceMismatchError):
        _open(tmp_path, source=b"different pdf bytes")

    new_source = b"different pdf bytes"
    rebound = _open(tmp_path, source=new_source, accept_source_change=True)
    assert rebound.stages == {}
    assert rebound.source_fingerprint == sha256_bytes(new_source)
    on_disk = json.loads((tmp_path / MANIFEST_NAME).read_text())
    assert on_disk["sourceFingerprint"] == sha256_bytes(new_source)
    assert on_disk["stages"] == {}


def test_make_stage_record_matches_commit_stage(tmp_path: Path) -> None:
    configs = {Stage.PHYSICAL: {"pipelineVersion": "1.2.3"}}
    workspace = _open(tmp_path, stage_configs=configs)
    _commit(workspace, Stage.INGEST)
    record = workspace.make_stage_record(
        Stage.PHYSICAL,
        producer_version=PRODUCER,
        artifacts={"physical.json": sha256_bytes(b"physical bytes")},
    )
    _commit(workspace, Stage.PHYSICAL)
    committed = workspace.stage_record(Stage.PHYSICAL)
    assert committed is not None
    assert record == committed


def test_commit_failure_keeps_manifest_unchanged(tmp_path: Path) -> None:
    workspace = _open(tmp_path)
    _commit(workspace, Stage.INGEST)
    # A non-empty directory at an artifact target makes the second replace
    # fail mid-commit, the filesystem-level stand-in for a crash.
    blocked = tmp_path / "resources"
    blocked.mkdir()
    (blocked / "keep.txt").write_bytes(b"old")

    with pytest.raises(OSError, match="Is a directory"):
        workspace.commit_stage(
            Stage.PHYSICAL,
            producer_version=PRODUCER,
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


def test_input_fingerprint_covers_config() -> None:
    inputs = {"physical.json": "hash"}
    assert input_fingerprint("1.0.0", inputs) != input_fingerprint(
        "1.0.0", inputs, {"registry": "a"}
    )
    assert input_fingerprint("1.0.0", inputs, {"registry": "a"}) != input_fingerprint(
        "1.0.0", inputs, {"registry": "b"}
    )
    assert input_fingerprint("1.0.0", inputs, {"a": "1", "b": "2"}) == input_fingerprint(
        "1.0.0", inputs, {"b": "2", "a": "1"}
    )


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
            artifacts={name: b"invalid"},
        )
    assert workspace.manifest_path.read_bytes() == before
