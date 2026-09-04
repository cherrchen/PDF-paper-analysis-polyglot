# Agent Note: M2 review repairs and renewed acceptance

Status: implemented

[中文](./2026-09-05-m2-review-repairs.md) | [English](./2026-09-05-m2-review-repairs.en.md)

## Problem

The 2026-09-05 code review found that the M2 Walking Skeleton passed the existing `just check` without meeting the roadmap exit gate. The viewer had no bidirectional click navigation, not every Tier-1 PDF compiled through the full pipeline, FigureRegion reading flow was incomplete, rotated-page transforms were wrong, translation and rendering bypassed frozen contracts, and the E2E tests did not run in clean-checkout CI.

This note supplements the existing [M2 Walking Skeleton implementation note](../architecture/2026-09-04-m2-walking-skeleton.en.md). It preserves the PDFium, basic recovery, LaTeX, and PDF.js choices while correcting the original completion evidence.

## Decision

Repair M2 against its original exit gate and accept it again:

1. Build per-page forward and inverse Physical page-space matrices for 0/90/180/270° rotation, and transform every PDFium object into top-left canonical space through those matrices.
2. Include text and figure regions in Layout reading flow, then build semantic structure from that complete flow.
3. Add canonical TranslationLayer and RenderDocument schemas and generated bindings. Translation writes only TranslationLayer, RenderComposer builds RenderDocument, and the LaTeX backend consumes only RenderDocument.
4. Remove illegal C0 controls at the PDF-text-to-LaTeX boundary, and compose each `CAPTION_OF` figure/caption pair into one render block and LaTeX float.
5. Recover RenderAnchors as hittable rectangles and provide versioned viewer data with source regions, semantic kinds, and target anchors.
6. Implement bidirectional click, highlight, and page switching in the viewer. Make `just test-e2e` compile fixtures, run the pipeline, and build the app itself, then execute it in the LaTeX CI job.
7. Restore strict Python type checks for both pipeline packages. Suppress Unknown diagnostics only in adapters that directly touch PDFium, whose type information is incomplete.

## Alternatives considered

- Keep M2 marked complete and defer defects to M3: this would build M3 on invalid coordinates, missing figures, and a false viewer acceptance signal.
- Change only documentation and call the missing functions limitations: roadmap phase 2.7 and the exit gate explicitly require real bidirectional navigation.
- Continue using a translated SemanticDocument copy: this violates the frozen origin-semantics and TranslationLayer identity model.

## Consequences

- All 11 Tier-1 fixtures pass the Physical→Layout→Semantic→Translation→Render→Target PDF pipeline.
- Source↔target mappings for Heading, Paragraph, and FigureCaption now have real Playwright click coverage; all four E2E tests pass.
- `just check` passes: 137 regular Python tests, 21 integration tests, golden, TypeScript, Rust, LaTeX, schema, and documentation gates are green; Python coverage is 94%.
- `just security` passes. `cargo deny` retains only its existing unmatched-license-allowance warnings. Zizmor is unavailable locally and remains enforced by its official CI action.
- TranslationLayer and RenderDocument extend the canonical schema set. Regenerating leaves generated artifact hashes unchanged, and the Python/TypeScript roundtrip covers both schemas.
- The M2 exit gate is closed again, and the roadmap proceeds to M3.
