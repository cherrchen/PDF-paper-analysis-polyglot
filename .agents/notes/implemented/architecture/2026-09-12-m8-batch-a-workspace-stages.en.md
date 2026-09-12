# Agent Note: M8 Batch A local workspace and stage-state contract

Status: implemented

[中文](./2026-09-12-m8-batch-a-workspace-stages.md) | [English](./2026-09-12-m8-batch-a-workspace-stages.en.md)

## Problem

When batch A (local workspace and stage state) of the [M8 admission closeout](../process/2026-09-12-m8-admission-closeout.en.md) started, `run_pipeline` was a one-shot monolithic function: artifacts were written only after every stage finished, so an interrupted process lost all progress; there was no record of a stage enum, stage status, producer versions, or input fingerprints; `docs/architecture/storage.en.md` still said "intentionally unresolved". Batch B's job orchestration, batch C's cache keys, and batch E's version migration all need a stage-state contract in place first.

## Decision

1. **New `pdf_pipeline.workspace` manifest module** (not under `apps/`). `workspace.json` is an ad-hoc manifest (same class as `probe.json`), deliberately **outside the frozen schemas** and the `just schema` flow; `workspaceVersion` is currently `0.1.0`.
2. **Stage enum** `INGEST → PHYSICAL → EVIDENCE → LAYOUT → SEMANTIC → TRANSLATE → RENDER → INDEX` (`Stage` / `STAGE_ORDER` / `STAGE_DEPENDENCIES`). Each stage records: status, artifact relative paths + sha256, producer version (reusing existing module version constants; RENDER/INDEX get new stage versions), and an input fingerprint (producer version + upstream record artifact hashes).
3. **Directory-level atomic commit**: artifacts are staged under `.staging/<stage>-<token>/`, replaced one atomic rename at a time, then `workspace.json` is rewritten atomically last — the manifest is the single commit pointer. After a failure or interrupt the manifest is unchanged, the next run treats the stage as unfinished and reruns it; a half-written artifact set is never accepted as success.
4. **Skip condition**: COMPLETED + every artifact hash verifies + the recorded input fingerprint matches the current upstream records. Re-committing an upstream stage (changed artifact hashes) transitively invalidates downstream stages.
5. **Figure resource binding moved into the SEMANTIC stage**: `semantic.json` now has a single owner (SEMANTIC), and its on-disk content is still the figure-bound version — the same on-disk contract as before. Translation only processes text nodes, so binding changes no translation artifact; a full run produces byte-identical output.
6. **The EVIDENCE stage persists per-provider bundles** (ad-hoc `evidence-bundles.json`) so a resumed LAYOUT stage does not re-run providers; `probe.json` is written at this stage instead of the end, with unchanged content.
7. **Strict rejection instead of migration**: an unknown `workspaceVersion`, an unparsable manifest, and a foreign source PDF (`sourceFingerprint` mismatch) are all explicit errors. Version migration belongs to batch E.

Current-state documentation: [`docs/architecture/storage.en.md`](../../../../docs/architecture/storage.en.md) (local workspace section closed, moving from "intentionally unresolved").

## Alternatives considered

- **RENDER overwrites `semantic.json` (keeping today's execution order)**: one file with two owners breaks hash-based stage verification; superseded by moving binding into SEMANTIC.
- **Modeling `workspace.json` in a frozen schema**: the manifest is a local implementation detail that will evolve with batches B/C; the frozen flow's cost is not justified.
- **Recomputing provider bundles on resume (no persistence)**: cheap with the mock registry, but network/heavy once batches D/E bring real adapters, violating "rerun only unfinished stages".
- **Trusting COMPLETED without artifact hash verification**: tampered or truncated artifacts would count as success, failing acceptance.
- **A dedicated subdirectory per stage with a completion marker**: a deeper tree that conflicts with the existing root-level canonical filename contract consumed by `rerender_workspace` and others.

## Consequences

- After an interrupt, restart reruns only unfinished stages; completed JSON/PDF artifacts are preserved as-is (`test_pipeline_resume.py` asserts this with per-stage call counts).
- Batch B can cut `run_pipeline` stages into resumable Jobs keyed by `Stage`; batch C can extend `input_fingerprint` with config/code versions; batch E can hook migration into `WorkspaceVersionError`.
- Translation-config changes currently do **not** invalidate the TRANSLATE stage (the fingerprint only covers upstream artifact hashes); this is a known batch C boundary, not a defect.
- The manifest stores a sha256 per artifact, so resume pays one re-read+hash per upstream artifact — acceptable at local scale.
- Verification: `just lint-python`, `just typecheck-python`, `just test-python` (450 passed; new `test_workspace.py` with 10 tests, `test_pipeline_resume.py` with 4 tests).
