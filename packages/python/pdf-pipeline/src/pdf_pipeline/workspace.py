# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false
"""Local workspace manifest and stage-state commit protocol (M8 batches A/C).

A workspace directory holds one document's pipeline artifacts together with
an ad-hoc ``workspace.json`` manifest — the same artifact category as
``probe.json``, deliberately outside the frozen schemas. The manifest
records, per pipeline stage (INGEST → PHYSICAL → EVIDENCE → LAYOUT →
SEMANTIC → TRANSLATE → RENDER → INDEX), the stage status, produced artifact
paths with content hashes, the producer version, and the input fingerprint.

The input fingerprint is the stage cache key: producer version + hashes of
every upstream artifact + the stage's configuration inputs (registry, parser
dump/command identity, translation config, render profile, schema and
pipeline versions). Changing any of them reruns exactly the stages that
consume that input; a stage whose recorded fingerprint still matches its
upstream records is skipped.

Commit protocol: stage artifacts are staged under ``.staging/`` and replace
their final paths one atomic rename at a time; ``workspace.json`` is
rewritten atomically **last**, so it is the single commit pointer. A crash
mid-commit leaves the manifest unchanged, and the next run treats the stage
as unfinished and reruns it — a half-written artifact set is never accepted
as success. On restart a COMPLETED stage is skipped only when every
recorded artifact still exists and still hashes to the recorded value.

``invalidate_from`` drops one stage's record plus every downstream record so
the next run reruns that tail (explicit local rerun). Version/source
handling is strict: an unknown ``workspaceVersion``, or a source PDF whose
fingerprint differs from the manifest, is an explicit error, never a silent
migration or silent reuse (migration belongs to M8 batch E). Rebinding a
workspace to different source bytes is opt-in via
``open_or_create(..., accept_source_change=True)`` and drops every stage
record.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import uuid
from contextlib import suppress
from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

WORKSPACE_VERSION = "0.1.0"

MANIFEST_NAME = "workspace.json"

STAGING_DIR = ".staging"


class StageStatus(StrEnum):
    """Lifecycle of one pipeline stage inside a workspace."""

    PENDING = "pending"
    COMPLETED = "completed"


class Stage(StrEnum):
    """Pipeline stages in execution order (docs/development/m8.md batch A)."""

    INGEST = "ingest"
    PHYSICAL = "physical"
    EVIDENCE = "evidence"
    LAYOUT = "layout"
    SEMANTIC = "semantic"
    TRANSLATE = "translate"
    RENDER = "render"
    INDEX = "index"


STAGE_ORDER: tuple[Stage, ...] = (
    Stage.INGEST,
    Stage.PHYSICAL,
    Stage.EVIDENCE,
    Stage.LAYOUT,
    Stage.SEMANTIC,
    Stage.TRANSLATE,
    Stage.RENDER,
    Stage.INDEX,
)

# Upstream stages whose committed artifacts feed each stage's input
# fingerprint. The source PDF itself is bound at manifest level via
# ``sourceFingerprint``, so INGEST depends on nothing.
STAGE_DEPENDENCIES: dict[Stage, tuple[Stage, ...]] = {
    Stage.INGEST: (),
    Stage.PHYSICAL: (Stage.INGEST,),
    Stage.EVIDENCE: (Stage.INGEST, Stage.PHYSICAL),
    Stage.LAYOUT: (Stage.INGEST, Stage.PHYSICAL, Stage.EVIDENCE),
    Stage.SEMANTIC: (Stage.INGEST, Stage.PHYSICAL, Stage.EVIDENCE, Stage.LAYOUT),
    Stage.TRANSLATE: (Stage.INGEST, Stage.PHYSICAL, Stage.EVIDENCE, Stage.LAYOUT, Stage.SEMANTIC),
    Stage.RENDER: (
        Stage.INGEST,
        Stage.PHYSICAL,
        Stage.EVIDENCE,
        Stage.LAYOUT,
        Stage.SEMANTIC,
        Stage.TRANSLATE,
    ),
    Stage.INDEX: (
        Stage.INGEST,
        Stage.PHYSICAL,
        Stage.EVIDENCE,
        Stage.LAYOUT,
        Stage.SEMANTIC,
        Stage.TRANSLATE,
        Stage.RENDER,
    ),
}


class WorkspaceError(RuntimeError):
    """Base error for workspace manifest problems."""


class WorkspaceVersionError(WorkspaceError):
    """The manifest was written by an incompatible workspace version."""


class WorkspaceSourceMismatchError(WorkspaceError):
    """The workspace belongs to a different source PDF."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def input_fingerprint(
    producer_version: str,
    inputs: Mapping[str, str],
    config: Mapping[str, str] | None = None,
) -> str:
    """Stable stage cache key: producer version + upstream hashes + config.

    ``inputs`` maps upstream artifact names to their content hashes;
    ``config`` maps this stage's configuration inputs (registry digest,
    parser dump digest, locale, render profile, schema/pipeline version, …)
    to a digest or literal value. Both mappings are sorted, so the key never
    depends on insertion order.
    """
    material = json.dumps(
        {
            "producerVersion": producer_version,
            "inputs": dict(sorted(inputs.items())),
            "config": dict(sorted((config or {}).items())),
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return sha256_bytes(material.encode("utf-8"))


@dataclass(frozen=True)
class StageRecord:
    """Manifest record of one stage's committed run."""

    status: StageStatus
    producer_version: str
    input_fingerprint: str
    artifacts: dict[str, str]  # workspace-relative path -> sha256

    def to_json(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "producerVersion": self.producer_version,
            "inputFingerprint": self.input_fingerprint,
            "artifacts": dict(sorted(self.artifacts.items())),
        }

    @classmethod
    def from_json(cls, data: object) -> StageRecord:
        if not isinstance(data, dict):
            raise WorkspaceError("stage record must be an object")
        status = data.get("status")
        if not isinstance(status, str) or status not in {
            StageStatus.COMPLETED.value,
            StageStatus.PENDING.value,
        }:
            raise WorkspaceError(f"unknown stage status: {status!r}")
        producer_version = data.get("producerVersion")
        input_fp = data.get("inputFingerprint")
        artifacts = data.get("artifacts")
        if not isinstance(producer_version, str) or not isinstance(input_fp, str):
            raise WorkspaceError("stage record requires producerVersion and inputFingerprint")
        if not isinstance(artifacts, dict) or not all(
            isinstance(key, str) and isinstance(value, str) for key, value in artifacts.items()
        ):
            raise WorkspaceError("stage artifacts must map paths to hashes")
        return cls(
            status=StageStatus(status),
            producer_version=producer_version,
            input_fingerprint=input_fp,
            artifacts=dict(artifacts),
        )


def _atomic_write_json(path: Path, data: object) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


class WorkspaceManager:
    """Manifest-backed access to one local workspace directory."""

    def __init__(
        self,
        root: Path,
        stage_configs: Mapping[Stage, Mapping[str, str]] | None = None,
    ) -> None:
        self.root = root
        self.manifest_path = root / MANIFEST_NAME
        self.source_fingerprint = ""
        self.stages: dict[Stage, StageRecord] = {}
        self._stage_configs: dict[Stage, dict[str, str]] = {
            stage: dict(values) for stage, values in (stage_configs or {}).items()
        }

    def _stage_config(self, stage: Stage) -> dict[str, str]:
        return self._stage_configs.get(stage, {})

    def open_or_create(self, source_bytes: bytes, *, accept_source_change: bool = False) -> None:
        """Load the existing manifest or initialize a fresh one for this source.

        A source fingerprint that differs from the manifest is an error unless
        ``accept_source_change`` is set: then every stage record is dropped and
        the workspace is rebound to the new source bytes, so the whole chain
        reruns against the new document.
        """
        fingerprint = sha256_bytes(source_bytes)
        if self.manifest_path.is_file():
            mismatch = self._load_existing(fingerprint)
            if mismatch is not None and not accept_source_change:
                raise mismatch
            if mismatch is not None:
                self.stages = {}
                self.source_fingerprint = fingerprint
                self._write_manifest()
        else:
            self.source_fingerprint = fingerprint
            self.stages = {}
            self._write_manifest()
        self.cleanup_staging()

    def _load_existing(self, source_fingerprint: str) -> WorkspaceSourceMismatchError | None:
        """Parse the on-disk manifest; return a mismatch instead of raising it.

        The caller decides whether a foreign source is fatal (default) or an
        accepted rebinding. Loading must not mutate anything first, so a
        rejected manifest leaves the in-memory state untouched.
        """
        try:
            payload = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise WorkspaceError(f"unreadable workspace manifest: {error}") from error
        if not isinstance(payload, dict):
            raise WorkspaceError("workspace manifest must be an object")
        version = payload.get("workspaceVersion")
        if version != WORKSPACE_VERSION:
            # Batch E owns migration; until then unknown versions are rejected.
            raise WorkspaceVersionError(
                f"workspace manifest version {version!r} is not supported "
                f"(expected {WORKSPACE_VERSION!r})"
            )
        recorded_source = payload.get("sourceFingerprint")
        mismatch = None
        if recorded_source != source_fingerprint:
            mismatch = WorkspaceSourceMismatchError(
                "workspace belongs to a different source PDF; "
                "remove the workspace or use a new output directory"
            )
        raw_stages = payload.get("stages")
        if not isinstance(raw_stages, dict):
            raise WorkspaceError("workspace manifest requires a stages object")
        stages: dict[Stage, StageRecord] = {}
        for name, record in raw_stages.items():
            try:
                stage = Stage(name)
            except ValueError:
                raise WorkspaceError(f"unknown stage in manifest: {name!r}") from None
            parsed = StageRecord.from_json(record)
            for artifact_name in parsed.artifacts:
                self._artifact_path(artifact_name)
            stages[stage] = parsed
        if mismatch is None:
            self.source_fingerprint = source_fingerprint
            self.stages = stages
        return mismatch

    def manifest_bytes(self) -> bytes:
        """Serialize records for inclusion in a wider workspace transaction."""
        payload = {
            "workspaceVersion": WORKSPACE_VERSION,
            "sourceFingerprint": self.source_fingerprint,
            "stages": {stage.value: record.to_json() for stage, record in self.stages.items()},
        }
        return (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8")

    def _write_manifest(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        _atomic_write_json(self.manifest_path, json.loads(self.manifest_bytes()))

    def _artifact_path(self, name: str) -> Path:
        path = PurePosixPath(name)
        if (
            not path.parts
            or path.is_absolute()
            or ".." in path.parts
            or path.as_posix() != name
            or path.parts[0] in {MANIFEST_NAME, MANIFEST_NAME + ".tmp", STAGING_DIR}
        ):
            raise WorkspaceError(f"invalid workspace artifact path: {name!r}")
        target = self.root / name
        if not target.resolve().is_relative_to(self.root.resolve()):
            raise WorkspaceError(f"artifact escapes workspace: {name!r}")
        return target

    def stage_record(self, stage: Stage) -> StageRecord | None:
        return self.stages.get(stage)

    def stage_completed(self, stage: Stage, producer_version: str | None = None) -> bool:
        """True only when committed, every artifact still verifies, and the
        recorded input fingerprint still matches upstream records and config.

        A committed stage whose upstream stage was recommitted (new artifact
        hashes) or whose stage configuration inputs changed is treated as
        unfinished so downstream output never goes stale.
        """
        record = self.stages.get(stage)
        if record is None or record.status is not StageStatus.COMPLETED:
            return False
        if producer_version is not None and record.producer_version != producer_version:
            return False
        for name, digest in record.artifacts.items():
            path = self._artifact_path(name)
            if not path.is_file() or sha256_bytes(path.read_bytes()) != digest:
                return False
        return record.input_fingerprint == input_fingerprint(
            record.producer_version, self._upstream_artifacts(stage), self._stage_config(stage)
        )

    def _upstream_artifacts(self, stage: Stage, *, required: bool = False) -> dict[str, str]:
        """Content hashes of every artifact committed by the stage's upstream.

        ``stage_completed`` reads this tolerantly — a missing upstream record
        simply means "not committed yet". ``commit_stage`` reads it strictly:
        a stage is only ever committed after its upstream committed, so a
        missing record there means the stage order was violated, never a
        silently empty input set.
        """
        inputs: dict[str, str] = {}
        for dep in STAGE_DEPENDENCIES[stage]:
            record = self.stages.get(dep)
            if record is None:
                if required:
                    raise WorkspaceError(f"upstream stage not committed: {dep.value}")
                return {}
            inputs.update(record.artifacts)
        return inputs

    def make_stage_record(
        self, stage: Stage, *, producer_version: str, artifacts: Mapping[str, str]
    ) -> StageRecord:
        """Build the record ``stage`` would get for these already-hashed artifacts.

        Callers that rewrite artifacts outside ``commit_stage`` (the
        rerender transaction) use this so their record carries the same
        cache key the next ``run_pipeline`` computes.
        """
        return StageRecord(
            status=StageStatus.COMPLETED,
            producer_version=producer_version,
            input_fingerprint=input_fingerprint(
                producer_version,
                self._upstream_artifacts(stage, required=True),
                self._stage_config(stage),
            ),
            artifacts=dict(artifacts),
        )

    def drop_stage_records(self, stage: Stage) -> None:
        """Drop ``stage`` and every downstream record in memory (no manifest write)."""
        dropped = STAGE_ORDER[STAGE_ORDER.index(stage) :]
        for dropped_stage in dropped:
            self.stages.pop(dropped_stage, None)

    def invalidate_from(self, stage: Stage) -> None:
        """Forget ``stage`` and every downstream stage, then persist the manifest.

        The next run reruns that tail; artifacts of the dropped stages stay on
        disk until each rerun overwrites its own declared paths.
        """
        self.drop_stage_records(stage)
        self._write_manifest()

    def commit_stage(
        self,
        stage: Stage,
        *,
        producer_version: str,
        artifacts: dict[str, bytes],
    ) -> None:
        """Atomically publish one stage's artifacts, then the manifest.

        Artifacts map workspace-relative paths to their bytes. Files are
        staged, each replaced via atomic rename, and only then does the
        manifest gain this stage's COMPLETED record with the cache key
        computed from upstream records and this workspace's stage config. Any
        failure before the manifest write leaves the manifest unchanged, so
        the next run reruns the stage instead of trusting half-written output.
        """
        record = self.make_stage_record(
            stage,
            producer_version=producer_version,
            artifacts={name: sha256_bytes(data) for name, data in artifacts.items()},
        )
        targets = {name: self._artifact_path(name) for name in artifacts}
        token = uuid.uuid4().hex
        staging = self.root / STAGING_DIR / f"{stage.value}-{token}"
        staged: list[tuple[Path, Path]] = []
        try:
            for name, data in artifacts.items():
                target = targets[name]
                target.parent.mkdir(parents=True, exist_ok=True)
                prepared = staging / name
                prepared.parent.mkdir(parents=True, exist_ok=True)
                prepared.write_bytes(data)
                staged.append((prepared, target))
            for prepared, target in staged:
                prepared.replace(target)
            previous = self.stages.get(stage)
            self.stages[stage] = record
            try:
                self._write_manifest()
            except BaseException:
                if previous is None:
                    self.stages.pop(stage, None)
                else:
                    self.stages[stage] = previous
                raise
        finally:
            shutil.rmtree(staging, ignore_errors=True)
            # Drop the staging parent too when this was its last entry, so
            # a committed workspace carries no staging residue.
            with suppress(OSError):
                staging.parent.rmdir()

    def cleanup_staging(self) -> None:
        """Remove staging directories left behind by an interrupted run."""
        shutil.rmtree(self.root / STAGING_DIR, ignore_errors=True)
