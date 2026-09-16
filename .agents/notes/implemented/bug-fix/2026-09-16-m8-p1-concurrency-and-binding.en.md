# Agent Note: M8 P1 concurrency and retranslation binding repairs

Status: implemented

[中文](./2026-09-16-m8-p1-concurrency-and-binding.md) | [English](./2026-09-16-m8-p1-concurrency-and-binding.en.md)

## Problem

The [M8 review](../../proposed/process/2026-09-16-m8-cross-boundary-review.en.md) found five P1 issues: shared Viewer publishers prune each other's revisions; retry deletes a newly claimed running record; failed claims leak descriptors; retranslation after import targets the startup workspace; jobs and retranslation lack a shared workspace lock. This note supplements the concurrency and binding contracts of [batch B](../architecture/2026-09-14-m8-batch-b-job-orchestration.en.md) and [batch F](../architecture/2026-09-16-m8-batch-f-local-e2e.en.md), retaining their history.

## Decision

1. Add `pdf_pipeline.locks`, deriving cross-process `flock` identities from canonical resource paths. Stable lock files live in the parent's `.paper-pipeline-locks/`, outside workspace and revision cleanup. Locks are reentrant within one thread; order is workspace → Viewer.
2. `run_pipeline` and `rerender_workspace` acquire the same workspace lock before reading artifacts, covering CLI, workers, API, and different jobs roots. The existing Job workspace lock remains for queue scheduling.
3. The Viewer lock covers reading the old manifest, revision creation, commit, rollback, and pruning. INDEX records the publication receipt under the same lock; receipt cache checks also read a locked snapshot.
4. Retry validates and migrates under the job lock, returning a state conflict on contention. Claim rereads queued under lock and releases descriptors not transferred to a claim in `finally`. Executor failure releases only cancelled tasks; running tasks release their own locks.
5. Manifests gain a server-authored absolute workspace binding. Browser retranslation sends revision; the API resolves the binding and checks revision both at resolution and final publication. Legacy manifests without bindings fall back to the startup workspace. INDEX producer advances to `0.2.0`, so existing workspaces need only republish the binding.

## Alternatives considered

- An API thread lock cannot protect another worker or CLI process.
- Holding the Viewer lock throughout computation unnecessarily serializes independent documents; protect only publication and receipts.
- Client-selected workspace paths cannot replace server-side revision binding.
- Removing lock files can create two distinct inodes and defeat exclusion.

## Consequences

- Add deterministic interleaving, descriptor, cross-process lock, API binding, and stale publication regressions. Product acceptance adds retranslation after importing a second document and rejection of its old revision.
- Current state: [storage](../../../../docs/architecture/storage.en.md) and [API](../../../../docs/architecture/api.en.md).
- Retain POSIX operation, local path import, workspace version, and canonical schemas; no golden updates.
- P2 first-page rendering failure is covered by a [separate repair note](2026-09-16-m8-p2-reader-load.en.md).
