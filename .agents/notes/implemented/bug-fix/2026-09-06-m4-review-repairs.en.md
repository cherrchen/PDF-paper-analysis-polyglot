# Agent Note: M4 review repairs

Status: implemented

[中文](./2026-09-06-m4-review-repairs.md) | [English](./2026-09-06-m4-review-repairs.en.md)

## Problem

The 2026-09-06 code review found that the M4 Semantic Recovery Engine had the modules and that `paper-anatomy` could recover the ten structural classes, but the exit gate closed too early. The named cross-page fixture was one page with two TeX paragraphs; the layout gate treated an author→date CONTINUATION as cross-page evidence; the semantic truth required `mergedParagraphNodes: 0`. FigureResource stored PhysicalObjectIDs in a ResourceID field. `FOOTNOTE_REFERENCE` stayed at `0.1.0` under a pre-freeze PATCH story after the M2 freeze. `[1-3]` citation ranges did not expand. Several tests checked the wrong objects or never asserted Abstract / section nesting. The roadmap marked GROBID and structured tables Done.

This note supplements the existing [M4 Semantic Recovery Engine implementation note](../architecture/2026-09-06-m4-semantic-recovery-engine.en.md). It does not rebuild the engine and does not install real GROBID / MinerU.

## Decision

Repair against the original exit gate and Review C:

1. Rewrite `cross-page-paragraph` as one paragraph on a short page so it paginates. The layout benchmark asserts a **cross-page** CONTINUATION edge. The semantic benchmark requires a merge and a multi-fragment anchor.
2. Leave `FigureResource.embeddedImageIds` empty until a ResourceStore exists. Do not treat PhysicalObjectID as ResourceID.
3. Record the schema-freeze exception: compatibility freeze started at the M2 exit gate; `FOOTNOTE_REFERENCE` is a MINOR-class additive enum that was not version-bumped. Later additive capabilities must bump MINOR. Update `docs/contracts/` freeze language.
4. Expand `[1-3]` / `[1–3]` citation ranges inclusively. Test unresolved and duplicate entries.
5. Support symbol footnote markers. Align the docstring with PDFium inserting a space before superscripts instead of pretending letter-glue exists. Empty FOOTNOTE regions still become nodes and report an issue.
6. SemanticValidator checks heading level jumps in document-tree order. A missing TABLE_CAPTION relation is `TABLE_RECOVERY`. Non-CITES dangling targets are `SOURCE_MAPPING`.
7. Repair weak tests: layer-separation checks layout↔semantic; bundle references use real SourceAnchors; determinism compares runs that both pass `lines=`; the benchmark asserts `frontMatterRoles` and `sectionParentOf`.
8. Pin the structured-table evidence path with a synthetic `TableCandidate`. The default mock still does not emit TABLE_STRUCTURE. Roadmap 4.4 / 4.7 mark specialists as deferred to M7.
9. Reclassify the four 2026-09-03 proposed architecture notes as rejected (absorbed by later implemented notes). They are no longer open proposals.

## Alternatives considered

- Keep M4 marked complete and leave the cross-page gate on the paper-anatomy Methods paragraph: the named fixture still cannot reproduce the 4.1 cross-page contract.
- Bump every schema to `0.2.0`: the wire shape did not change, and every fixture / golden / Literal version would churn. Record the exception and freeze upgrade discipline instead.
- Implement letter-glue that rejects whitespace-separated digits: PDFium extracts `\footnote` as `footnote 1`, which would drop real references.
- Wire GROBID / MinerU now: heavy dependencies and unreproducible environments still fail the bar. Keep the deterministic baseline.

## Consequences

- The M4 exit gate closes after these review repairs: cross-page paragraphs, Abstract, L2 nesting, citation ranges, Source Mapping, and validator level-jumps have mechanical assertions.
- Known limits remain on the M4 implementation note: 1 Layout → N Semantic, true multi-column tables, GROBID author-year citations, figure PDF/SVG/raster resources, and MathML stay with M5/M7.
- Second-round correctness gaps (dropped table titles, stale marks, wrong footnote links, cyclic-tree crashes, truncated viewer mapping, empty provenance) are covered in the [M4 correctness-repairs note](2026-09-06-m4-correctness-repairs.en.md).
