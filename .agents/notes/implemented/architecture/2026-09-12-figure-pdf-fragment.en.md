# Agent Note: Figure PDF-fragment originals

Status: implemented

[中文](./2026-09-12-figure-pdf-fragment.md) | [English](./2026-09-12-figure-pdf-fragment.en.md)

## Problem

Vector figures without embedded rasters (for example `tikz-vector`) became empty `\fbox` after M5 resource extraction. FR-FIG-001 / FR-FIG-005 / PRD §43 require restoring or cropping figure assets and keeping the original. SVG as true-source is not an FR.

## Decision

1. **Crop the source PDF page to the figure-region bbox** as `PDF_FRAGMENT` (`ResourceKind` already exists). Bind `FigureResource.pdfFragmentResourceId`; keep existing `embeddedImageIds`.
2. **Projection selects one representation:** PDF fragment if usable, otherwise embedded rasters, otherwise an empty-box Issue. Both asset kinds stay on `FigureResource` but must not be projected together. LaTeX uses the existing `graphicx` package for `.pdf`. **No SVG export.** `VectorObject` may still store geometry only; the asset true-source is the page crop. Multiple rasters with no fragment still stack. See [M8-pre review repairs](../bug-fix/2026-09-12-m8-pre-review-repairs.en.md).
3. **No new TeX packages.** `rerender_workspace` consumes the already-written `resources.json` and does not re-crop (FR-TRANS-004, zero source re-parsing).

## Alternatives considered

- Convert paths to SVG as true-source: not an FR; adds a second backend and font issues.
- Rasterize vector figures only: loses vectors and violates “keep the original asset”.
- Keep the empty box as an observable failure: does not satisfy FR-FIG-001.

## Consequences

- `tikz-vector` compiles `\includegraphics{...pdf}`; `figure-caption` rasters are still extracted and bound.
- Current state: [`docs/architecture/rendering.en.md`](../../../../docs/architecture/rendering.en.md).
- This lands the FR-FIG closeout in [PRD filters roadmap deferrals](../process/2026-09-12-prd-filters-roadmap-deferrals.en.md) without a multi-renderer architecture.
