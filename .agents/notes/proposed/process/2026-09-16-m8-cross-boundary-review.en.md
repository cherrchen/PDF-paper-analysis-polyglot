# Agent Note: M8 cross-boundary acceptance proposal

Status: proposed

[中文](./2026-09-16-m8-cross-boundary-review.md) | [English](./2026-09-16-m8-cross-boundary-review.en.md)

## Problem

Review of M8 A–F (`750e14d..7f8ce7e`) found shared state not covered by individual batch success paths or serial product acceptance. The workspace lock in [batch B](../../implemented/architecture/2026-09-14-m8-batch-b-job-orchestration.en.md) does not protect a shared Viewer publication directory. Import switching in [batch F](../../implemented/architecture/2026-09-16-m8-batch-f-local-e2e.en.md) does not cover partial retranslation of the new document.

Temporary deterministic interleaving probes on 2026-09-16 reproduced three problems: 20 failed claims for a queued job sharing a busy workspace added 20 open file descriptors; a worker claiming immediately after retry publishes the queued record loses its running record to retry cleanup; a second publisher can prune the first publisher's uncommitted revision, leaving the final manifest pointing to a missing directory. These probes exercise implementation paths but are not yet repository regression tests.

## Proposal

Organize follow-up acceptance around shared resources: enumerate every writer and lock boundary for Job transitions, workspace writes, and Viewer publication. Add deterministic interleaving tests for each boundary while retaining real LaTeX and browser success paths. Add partial retranslation after importing a second document and reader page-render failure acceptance.

## Alternatives considered

- Add only serial end-to-end tests: they cannot reliably exercise record migration and revision pruning races.
- Add only random stress tests: useful for discovery, but insufficient as the sole regression evidence for known interleavings.
- Rewrite existing implemented notes as unfinished: loses history; this proposal supplements acceptance while retaining original decisions.

## Acceptance criteria

- Lock contention and exception paths do not leak file descriptors; interleaved retry, claim, and query operations do not lose job records.
- Two workspaces sharing a Viewer directory always expose manifests referencing complete existing revisions; rollback never overwrites another publisher's successful result.
- Jobs and retranslation use one consistent cross-process exclusion protocol for the same workspace.
- Partial retranslation after importing a second document operates on that document's workspace; first-page rendering failures restore the previous reader state.
- Fixes pass relevant `just` checks, with local checks, remote CI, and real parser verification reported separately.

## Risks

Overly broad locks would serialize computation for independent documents; exclusion should cover actual shared writes. This proposal implements no fixes and does not change the M8 real-parser admission boundary.

P1 repairs landed in a [separate repair note](../../implemented/bug-fix/2026-09-16-m8-p1-concurrency-and-binding.en.md); the long-term acceptance process remains pending.

The P2 first-page transaction is also implemented in a [separate repair note](../../implemented/bug-fix/2026-09-16-m8-p2-reader-load.en.md); the long-term acceptance process remains proposed.
