# Agent Note: PRD filters roadmap deferrals

Status: implemented

[中文](./2026-09-12-prd-filters-roadmap-deferrals.md) | [English](./2026-09-12-prd-filters-roadmap-deferrals.en.md)

## Problem

After the M7 baseline landed, the roadmap “recommended next steps” bound a leftover list as the gate into M8: real MinerU/Docling/GROBID adapters, region-level annotated truth, `source-derived` / `dense-two-column` profiles, MathML, PDF/SVG figure assets, character-level mapping, and the annotation layer. Several of those items conflict with PRD v0.2 Initial Product boundaries or are not FRs at all. [PRD v0.2](./2026-09-06-product-requirements-v02.en.md) already requires downstream plans to treat the PRD as upstream; leaving the list unfiltered would treat Post-Initial / NG items as debt.

## Decision

1. **PRD v0.2 filters the leftover list.** “Must finish before M8” on the roadmap must not include NG items, Post-Initial work (§44: not a current-milestone acceptance requirement), or unnamed encoding details. The table in this note is the authoritative filter; current state is [`docs/development/roadmap.en.md`](../../../../docs/development/roadmap.en.md).
2. **Removed from the leftover list (not Initial Product):**
   - Character-level mapping — [PRD NG4](../../../../docs/product/requirements.en.md), FR-SYNC-005, §43 “Character Mapping: not required”. Identity and sync stay at SemanticNode; `SourceFragment` remains `LayoutRegionRef` only.
   - `source-derived` / `dense-two-column` — FR-LAYOUT-004 default single column; §43 “inheriting source two-column: not required for v1”; R2 is Post-Initial. Default remains `readable-single-column`. Continues the v0.2 note’s ruling on `SourceDerivedProfile`.
   - Annotation layer — PRD §47 future extension; §43 SemanticDocument user editing is unsupported in v1. There is no `FR-ANN-*`. Region-level **annotated truth** (benchmark ground truth) is not the derived Annotation layer.
   - MathML as a named leftover deliverable — FR-EQ-002 asks for a re-typesettable math representation and does not name MathML. `latex` / `unicodeText` / `rawText` cover v1; the schema `mathml` field stays, copied when an adapter emits it, not a separate milestone.
3. **Still required before M8 (PRD-aligned):**
   - Real MinerU / Docling / GROBID adapters — PRD §34; third parties emit Evidence only. Default CI uses recorded dumps; live services are optional extras. The default capability registry stays `mock` / `docling-sim` / `grobid-sim`.
   - Region-level annotated truth — engineering prerequisite for M7 region precision and numeric calibration, not user Annotation.
   - Vector figure PDF fragments — FR-FIG-001 / FR-FIG-005 / §43 “keep the original asset”. SVG-as-true-source is not an FR and is not delivered.
4. **Do not rewrite historical landing notes.** “Deferred at the time” sentences in implemented M5/M6/M7 notes stay; they cross-link here. Current-state docs and the roadmap progress section state the filtered facts.

## Alternatives considered

- Implement the entire original leftover list before M8: would treat NG4, R2, and §47 as v1 acceptance, violating the PRD-as-upstream rule.
- Change only the “next steps” sentence while detail rows still say “unimplemented character-level / MathML”: the debt reading remains and agents would keep treating them as must-dos.
- Treat MathML / SVG as implied by FR-EQ / FR-FIG: the PRD wants re-typesettable equations and original figure assets; LaTeX plus PDF fragments cover that; named encodings are not requirements.

## Consequences

- The gate into M8 narrows to three PRD-aligned gaps; landing notes are [optional real parser adapters](../architecture/2026-09-12-optional-parser-adapters.en.md), [region-level layout truth](../architecture/2026-09-12-region-level-layout-truth.en.md), and [figure PDF fragments](../architecture/2026-09-12-figure-pdf-fragment.en.md). Correctness closeout is [M8-pre review repairs](../bug-fix/2026-09-12-m8-pre-review-repairs.en.md); misnamed semantic-accuracy metrics are not acceptance evidence. Admission grades: [M8 admission closeout](./2026-09-12-m8-admission-closeout.en.md).
- Current-state pages no longer describe character-level mapping, two-column profiles, the Annotation layer, or standalone MathML as unpaid debt.
- This decision supplements rather than replaces [PRD v0.2](./2026-09-06-product-requirements-v02.en.md).
