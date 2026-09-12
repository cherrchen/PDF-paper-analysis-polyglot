# Agent Note: M8 batch A review repairs

Status: implemented

[中文](./2026-09-12-m8-batch-a-review-repairs.md) | [English](./2026-09-12-m8-batch-a-review-repairs.en.md)

## Problem

Batch A resumed from an untracked build PDF, compared producer versions with themselves, and skipped missing or newly requested viewer destinations. Partial retranslation did not update the manifest or root PDF, so resume overwrote its output. Manifest write failures left premature in-memory completion; invalid status types leaked TypeError.

## Decision

Complete the [batch A contract](../architecture/2026-09-12-m8-batch-a-workspace-stages.en.md): resume uses the committed PDF and current producer versions. INDEX saves a receipt checking the destination and publication hashes. Partial retranslation includes new stage records and the root PDF in the existing rollback transaction and invalidates INDEX. Failed manifest writes restore memory; invalid status and UTF-8 raise WorkspaceError. Current state: [storage](../../../../docs/architecture/storage.en.md). Configuration cache keys remain batch C.

## Alternatives considered

- Always compile and translate again: loses resume benefits and overwrites user retranslation.
- Always publish the viewer: produces unnecessary revisions; use a hash receipt instead.
- Write the manifest separately after retranslation: risks inconsistent records on failure; reuse the publication rollback transaction.

## Consequences

Add regressions for resume, producer upgrades, viewer repair, retranslation preservation, and manifest failures. The first resume after partial retranslation rebuilds INDEX. No frozen schema or golden changes.

Artifact paths must stay inside the workspace and cannot overwrite manifest or staging reserved paths; both manifest loading and commit validate them.
