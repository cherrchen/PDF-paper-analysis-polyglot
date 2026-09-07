# Agent Note: M5 review repairs

Status: implemented

[中文](./2026-09-08-m5-review-repairs.md) | [English](./2026-09-08-m5-review-repairs.en.md)

## Problem

The 2026-09-08 code review refused to accept M5. Declared translation, figure-resource, equation, table, CJK, and RenderAnchor capabilities lost content, failed to compile, or mapped the wrong objects on the real path; the green tests did not cover those cases. This note supplements the existing [M5 Translation & Rendering Pipeline implementation note](../architecture/2026-09-08-m5-translation-rendering-pipeline.en.md). It does not redo schemas and does not add MathML, a two-column profile, or 1→N Semantic.

## Decision

1. **Translation protection**: `OpenAICompatProvider` replaces CITATION / equation marks with placeholders before the model request and rejects dropped placeholders. The dummy path is unchanged.
2. **Terminology cache**: real providers hash glossary content into `terminologyRevision`, so editing a manual preferred translation busts the cache.
3. **Provider config**: `create_provider(provider_config=...)` and `run_pipeline(translation_config=...)` use the passed config. They do not re-read environment variables and override the endpoint or model.
4. **CJK**: `generic-academic.tex` loads `luatexja-fontspec` plus FandolSong so default `zh-CN` translations render. Regression checks the compile log for Missing character.
5. **Equations**: unicode substitutions add `{}` command boundaries; unsafe input falls back to `\text{...}`; `equation.number` is preserved with `\tag`.
6. **Figure resources**: extract FlateDecode bitmaps (bitmap→PNG without Pillow); ResourceIDs match physical `imageObject` ids; bind via layout `physicalObjectIds` and never guess by global index; failed extracts record an Issue and an observable empty box.
7. **Float anchors**: start/end hypertargets for figures and tables live inside the float so they move with the content.
8. **Tables**: `floatTables=False` uses `\captionof` (ABOVE and BELOW); project the full grid including `rowSpan`/`colSpan` and missing columns; `SCALE_FONT` uses `\fitbox`.
9. **Overflow**: default `SCALE_DOWN` equations use `\fitmath`; wide tables scale only when they exceed `\linewidth`.
10. **Image paths**: resolve to absolute paths before writing TeX so a relative `out_dir` still compiles from `build/`.
11. **RenderAnchor**: interpolate start/end hypertargets into per-page content-area geometry instead of two 12×12 endpoint hit boxes.

## Alternatives considered

- Keep filling figure N from global image N: header images, vector figures, and skipped rasters would swap captions.
- Use `ctex` for Chinese: the dependency set includes beamer / xetex / uplatex, which is too large for CI. `luatexja` + `fandol` is enough to display and break CJK.
- Add Pillow for bitmap extract: keep the dependency set small. PDFium bitmaps plus a stdlib PNG encoder are enough.
- Leave figure/table anchors at the body insertion point: jumps land on the wrong page after the float moves.

## Consequences

- M5 acceptance blockers (protected text, missing CJK glyphs, illegal math commands, dropped rasters, cross-page fragments, wrong figure binding, float anchors, equation renumbering) have mechanical tests.
- Deferred work is unchanged: MathML, `dense-two-column`, 1 Layout → N Semantic, and true PDF/SVG figure assets.
- Current state: [rendering](../../../../docs/architecture/rendering.en.md); packages: [LaTeX](../../../../docs/development/latex.en.md).
