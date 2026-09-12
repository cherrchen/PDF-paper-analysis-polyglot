# Agent Note: M8-pre review correctness repairs

Status: implemented

[中文](./2026-09-12-m8-pre-review-repairs.md) | [English](./2026-09-12-m8-pre-review-repairs.en.md)

## Problem

The 2026-09-12 review before M8 found that trunk regressions passed while new behavior still had reproducible correctness bugs, so “all pre-M8 gaps are closed” is not an acceptance claim. Figure projection emitted both a PDF fragment and embedded rasters; Docling `l/t/r/b` ignored `coord_origin`, so BOTTOMLEFT boxes got a negative height and were dropped; `grid` expanded merged cells twice; MinerU formula IDs used only the in-page `block_index` and collided across pages; the live GROBID path POSTed raw `application/pdf` instead of multipart `input` for `processFulltextDocument`; `paragraphRecoveryAccuracy` / `sectionHierarchyAccuracy` were layout-label recall. This note supplements the [M7 landing note](../architecture/2026-09-12-m7-parser-ensemble.en.md), [optional real parsers](../architecture/2026-09-12-optional-parser-adapters.en.md), [region-level layout truth](../architecture/2026-09-12-region-level-layout-truth.en.md), and [figure PDF fragments](../architecture/2026-09-12-figure-pdf-fragment.en.md) without rewriting their historical decision sentences.

## Decision

1. **Project one figure representation.** `FigureResource` still keeps both `pdfFragmentResourceId` and `embeddedImageIds`. `figure_resource_ids` selects against the available set: the fragment if usable, otherwise rasters. Multiple rasters with no fragment still stack and record an Issue. Reordering the list is not enough.
2. **Convert Docling coordinates into canonical space.** `parse_rect` reads `coord_origin` on `l/t/r/b` boxes; BOTTOMLEFT flips with page height into top-left (the repo canonical space). Both origins are covered.
3. **Deduplicate merged cells.** Prefer Docling `table_cells` start/end offsets; when only `grid` exists, emit the span origin once. Do not create one spanned cell per covered grid slot.
4. **Formula IDs include the page.** MinerU `derived_id` is `formula-{pageId}-{block_index}`, with a two-page regression.
5. **GROBID live requests match the API.** `POST /api/processFulltextDocument` uses `multipart/form-data` with the PDF in `input`. A local HTTP stub checks path, headers, and body.
6. **Name the metrics honestly.** `paragraphLabelRecall` / `headingLabelRecall` are `PARAGRAPH_LIKE` / `HEADING_LIKE` region recall; they do not score paragraph merge/split, heading level, or section parent/child. `semanticExpectationCoverage` remains kinds / minCounts. Those numbers are not semantic-capability closeout evidence. Baseline keys rename with the contract; values stay the same.
7. **Contract tests over single-page happy paths.** Fixtures follow Docling-core v2.48 fields (`coord_origin`, `table_cells`, spanned `grid`) and MinerU multi-page `pdf_info`. The live path uses an HTTP stub, not Java/models.
8. **Quality follow-up.** Dump/process I/O lives in `native.py`; one PDFium document is reused for fragment crops; adapter files no longer carry file-level pyright exemptions (the JSON boundary stays in `native.py`).

## Alternatives considered

- Keep both IDs in `resourceIds` with fragment first: `figure-caption` already emitted two `\includegraphics` commands.
- Use `abs(b-t)` for BOTTOMLEFT: height becomes positive, but `y` stays at the PDF top edge and the box lands on the wrong side of the page.
- Keep walking `grid` using `row`/`column`: Docling repeats the same cell across the span, so a second `colSpan=2` cell crosses the table boundary.
- Add real paragraph/section semantic truth and keep the old names: out of scope here; the wrong names would keep treating layout recall as semantic accuracy.

## Consequences

- Current state: [`docs/architecture/rendering.en.md`](../../../../docs/architecture/rendering.en.md), [`docs/development/roadmap.en.md`](../../../../docs/development/roadmap.en.md) 7.6 / 4.3, [`docs/contracts/parser-adapter-contract.en.md`](../../../../docs/contracts/parser-adapter-contract.en.md), [`docs/testing/fixtures.en.md`](../../../../docs/testing/fixtures.en.md).
- The three PRD surfaces (real adapters, region truth, PDF fragments) still exist, but “fully closed” must not be written as M8 entry until these correctness repairs landed. Admission grades and the v1 plan: [M8 admission closeout](../process/2026-09-12-m8-admission-closeout.en.md).
- Baseline key rename follows the golden policy: same numbers, new names, because label recall must not be called semantic accuracy.
