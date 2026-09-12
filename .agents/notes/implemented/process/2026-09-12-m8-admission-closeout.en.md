# Agent Note: M8 admission closeout and v1 scope

Status: implemented

[中文](./2026-09-12-m8-admission-closeout.md) | [English](./2026-09-12-m8-admission-closeout.en.md)

## Problem

The three PRD surfaces before M8 already had implementations and review repairs, but progress docs collapsed “implemented”, “synthetic fixture passed”, and “real-tool verified” into one “closed” sentence. `just benchmark` ran only on nightly after a second TeX install, not in PR CI / `CI / gate`. Real MinerU / Docling / GROBID output was not exercised through adapter → normalize/fusion → semantic recovery. Without an M8 v1 scope ruling, the roadmap still treated Typst, HTML, and the Analysis Layer as the same milestone’s mandatory work. This note supplements [PRD filters roadmap deferrals](./2026-09-12-prd-filters-roadmap-deferrals.en.md), [optional real parser adapters](../architecture/2026-09-12-optional-parser-adapters.en.md), [region-level layout truth](../architecture/2026-09-12-region-level-layout-truth.en.md), [figure PDF fragments](../architecture/2026-09-12-figure-pdf-fragment.en.md), and [M8-pre review repairs](../bug-fix/2026-09-12-m8-pre-review-repairs.en.md) without rewriting their historical decision sentences.

## Decision

1. **Grade admission evidence; do not mix labels.** Current-state docs may only use: implemented, synthetic fixture passed, real-tool verified. The authoritative checklist and whether each item blocks M8 live in [`docs/development/m8.en.md`](../../../../docs/development/m8.en.md).
2. **PR CI runs `just benchmark`.** The Python reusable workflow calls that recipe after the existing `just latex-smoke` and `just test-python`; `CI / gate` already depends on the python job, so a quality regression blocks merge. `just ci` lists `benchmark` as a dependency. Nightly reuses `ci-python.yml` and drops the duplicate TeX-install benchmark job. Never reset the baseline or update golden to go green. The comparator must fail on a missing fixture, a measurable metric becoming null, a metric drop, or an ERROR/FATAL increase; calibration accuracy stays diagnostic. This is a fact update to the consequences of [Git and CI governance](./2026-09-03-git-and-ci-governance.en.md), not a change to trunk development or split workflows.
3. **Record the real-parser gap honestly.** Synthetic dumps stay as contract tests and now also run adapter → normalize/fusion → semantic. On 2026-09-12 MinerU/Docling were not installed and `GROBID_URL` was unset; do not invent recordings. The production capability registry remains `mock` / `docling-sim` / `grobid-sim`. Switching a registry primary to a real parser, and the user-facing replacement entry, belong to M8 batch E, not this round.
4. **M8 v1 scope.** v1 is local workspace persistence, task recovery, incremental reprocessing, caching, specialist failure isolation, old-workspace migrate-or-refuse, and parser access configuration. Typst, HTML, and the Analysis Layer are later extensions per PRD §44 / R7–R8. Do not reintroduce scanned OCR, character-level mapping, two-column translation PDFs, Annotation, or standalone MathML. `paragraphLabelRecall` / `headingLabelRecall` keep their layout-label-recall meaning. The batched plan’s home is [`docs/development/m8.en.md`](../../../../docs/development/m8.en.md).

## Alternatives considered

- Keep writing “the three surfaces have landed” as the M8 entry claim: treats synthetic contracts as real parser end-to-end.
- Hand-author JSON that merely looks official and label it recorded: forged evidence.
- Add MinerU/Docling/GROBID to default dependencies or CI: violates optional extras and the heavy-native rule.
- Wait for live tools before starting M8: keeps PRD Local-first workspace/cache/resume work blocked on parser daemons.
- Give PR CI a second TeX install just for benchmark: duplicates `ci-python.yml` smoke.

## Consequences

- Admission: M8 v1 batches A–D may start; real-tool parser verification has not passed, so it blocks production registry replacement, not local workspace work.
- Current state: [`docs/development/m8.en.md`](../../../../docs/development/m8.en.md), [`docs/development/roadmap.en.md`](../../../../docs/development/roadmap.en.md), README, parser contract, and fixture pages.
- Dump grades: `tests/fixtures/parser-dumps/provenance.json`.
