# Agent Note: Region-level layout truth

Status: implemented

[中文](./2026-09-12-region-level-layout-truth.md) | [English](./2026-09-12-region-level-layout-truth.en.md)

## Problem

M7 Region Precision and numerical calibration treated `readingOrder` snippets as region hits: recovered regions missing from the snippet list could not count as negatives, and `paragraphRecoveryAccuracy` / `sectionHierarchyAccuracy` stayed null. That is not a user Annotation layer; PRD §47 leaves Annotation out of v1.

## Decision

1. **`layout-truth.regions[]` is benchmark ground truth, not an Annotation layer.** Each entry stores `pageIndex`, `LayoutLabel`, canonical `geometry`, and optional `textPreview`. Do not use drifting `LayoutRegionID`s. Keep `readingOrder` for order regression.
2. **Match rule:** IoU ≥ 0.5 and matching labels (use `region.labels[0].label`, not `kind`). HEADER/FOOTER are excluded from the recovered set. Uncertain boxes stay out; never freeze current output as precision=1.0.
3. **Once labels exist:** `quality_report` uses labeled metrics; `paragraphRecoveryAccuracy` / `sectionHierarchyAccuracy` score `PARAGRAPH_LIKE` / `HEADING_LIKE`. Calibration samples become fused confidence vs IoU hit.
4. **Calibration stays diagnostic.** Sparse-truth is no longer the exemption; the report audits the fusion formula, not the product gate. `compare()` never marks calibration accuracy as `REGRESSED`. See decision 10 in the [M7 landing note](./2026-09-12-m7-parser-ensemble.en.md) for the original wording; this note replaces the “region-level truth does not exist yet” precondition.
5. **Baseline updates follow the golden policy.** Changing truth granularity will change numbers; the commit must say why, never rewrite the baseline merely to go green.

## Alternatives considered

- Treat a Viewer Annotation layer as GT: violates PRD §47 / there is no `FR-ANN-*`.
- Keep snippet matching as fake precision: cannot calibrate, cannot tell misses from extras.
- Freeze every recovered box into `regions[]`: precision stays 1.0 and the metric is useless.

## Consequences

- Fixture convention: [`docs/testing/fixtures.en.md`](../../../../docs/testing/fixtures.en.md). Draft script `scripts/seed_layout_truth_regions.py` exports snippet hits plus FIGURE/TABLE/FORMULA only.
- `author-year-citations` now has layout-truth.
- `tests/benchmark/baseline.json` is updated because truth granularity changed from snippets to IoU+label: the old regionRecall=1.0 was snippet matching, not region precision; the new numbers are lower but honest. `paragraphRecoveryAccuracy` / `sectionHierarchyAccuracy` become measurable instead of null. Calibration stays diagnostic.
- This supplements [PRD filters roadmap deferrals](../process/2026-09-12-prd-filters-roadmap-deferrals.en.md) and does not rewrite historical M7 sentences.
