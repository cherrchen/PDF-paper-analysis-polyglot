# Agent Note: M7 review repairs

Status: implemented

[中文](./2026-09-12-m7-review-repairs.md) | [English](./2026-09-12-m7-review-repairs.en.md)

## Problem

The 2026-09-12 code review requested changes: M7 unit tests passed, but the Exit Gate still failed under minimal reproductions. `fuse_page` voted one candidate at a time, so normalized share was always 1 and authority weights cancelled; TABLE/FORMULA used a fixed weight; `authorities()` dropped empty slots then ranked by index, promoting fallback / unlisted providers to challenger. The benchmark treated a missing fixture or a metric becoming null as unchanged; calibration diagnostics were marked `REGRESSED`; the error gate read only `SECTION_STRUCTURE`. 1→N splits broke cross-page continuation; segmentation used a loose regex, so math lines still split paragraphs. This note supplements the [M7 landing note](../architecture/2026-09-12-m7-parser-ensemble.en.md). It does not add real parser adapters or region-level labeled truth.

## Decision

1. **Cross-provider arbitration**: `fuse_page` clusters candidates for the same region first (including TABLE/FORMULA), then calls `fuse_candidate_labels` once. Page-level tests: swapping the `layout.region` / `formula.detection` primary changes the winner; a 0.1 vs 0.9 conflict does not give both a fused share of 1.0.
2. **Role weights**: `authority_rank` uses primary / challenger / fallback slots; unlisted is always rank 3. In the default registry `TABLE/mock` is 1.0 (fallback) and `FORMULA/unknown` is 0.8.
3. **Gate**: a baseline fixture missing from the current report is `REGRESSED`; a previously measurable metric becoming null is `REGRESSED`. Calibration accuracy is emitted as `diagnostic` lines only. `issues` reports both `byCategory` and `bySeverity`; the blocking count is ERROR+FATAL. WARNING/INFO are observed, not gated.
4. **Metric names**: the kinds / minCounts check is `semanticExpectationCoverage`. `paragraphRecoveryAccuracy` and `sectionHierarchyAccuracy` stay null without region-level truth.
5. **Continuation and math guard**: after a 1→N split in a continuation group, non-heading boundary pieces still join and SourceAnchors keep every source region. Split decisions reuse `heading_decision`, so `2 dx = dy` no longer tears one paragraph into three.
6. **Other follow-up**: `load_registry()` returns a read-only mapping; `columns_separated` hoists column clustering out of the span loop; `pipeline.en.md` records the M7 routing paragraph.

## Alternatives considered

- Keep per-candidate fusion and only add unit tests: the reproduction still showed identical results after swapping primary, so the Exit Gate would stay a false green.
- Keep relative calibration drops as a gate: that contradicts “calibration is diagnostic only”, and correctly recovered but unlabeled regions can cause a drop.
- Keep `SECTION_STRUCTURE` as the error proxy: ERROR issues in other categories would slip through.

## Consequences

- Phase 7.4 authority weights can now change the `fuse_page` winner; the 7.7 gate fails when fixtures or measurable metrics disappear.
- Verification: `just test-python` 408 passed, 90.10% coverage; Python lint, Pyright, and bilingual checks passed. Full CI and `just benchmark` were not a blocking run for this repair.
- Current state: the [M7 landing note](../architecture/2026-09-12-m7-parser-ensemble.en.md), [`docs/architecture/pipeline.en.md`](../../../../docs/architecture/pipeline.en.md), and [`docs/development/roadmap.en.md`](../../../../docs/development/roadmap.en.md) M7 detail rows.
