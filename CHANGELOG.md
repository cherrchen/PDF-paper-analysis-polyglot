# Changelog

All notable released changes will be documented here.

The project is `v0.x`. Architecture is unstable. Release notes are produced at tag time from pull request titles and Agent Notes. Do not update this file on every internal commit.

## Unreleased

### Added

- M1 core document contracts: six canonical JSON Schemas (common, physical-document, evidence, layout-document, semantic-document, mapping) at version 0.1.0, with deterministic TypeScript and Pydantic bindings, schema fixtures, layer-responsibility validators, and cross-language roundtrip tests.
- Polyglot repository bootstrap: workspaces, LaTeX / LuaLaTeX rendering toolchain, quality gates, Agent governance, and CI foundations.
- M2 walking skeleton: PDFium physical backend with deterministic IDs (`pypdfium2`); minimal layout recovery (gutter-based column detection, linear reading flow); minimal semantic recovery (HEADING/PARAGRAPH/FIGURE with caption binding); dummy translation provider; generic-academic LaTeX renderer with render anchors and a full pipeline CLI; dual-pane PDF viewer (`pdfjs-dist`) with mapping-driven navigation and Playwright e2e coverage.
- M3 layout recovery engine: vector path extraction in the physical backend; `EvidenceProvider` adapter boundary with `MockLayoutEvidenceProvider` and coordinate/label normalization; region fusion (IoU/containment matching, confidence-weighted label votes, TABLE/FORMULA absorption); recursive XY-cut band and column recovery with graphics clustering; structure-driven reading flow with continuation edges; layout-level caption association (`FIGURE_BLOCK`/`TABLE_BLOCK`) and footnote recovery (`FOOTNOTE_FLOW` outside `primaryFlow`); pipeline wiring for evidence, captions, footnotes, and identity-based source anchors; layout benchmark with hand-derived ground truth for all 11 Tier-1 fixtures (region recall, pairwise ordering, caption/footnote assertions).
- M4 semantic recovery engine: CONTINUATION-driven paragraph merging with multi-fragment SourceAnchors (`attributes.layoutRegionIds`); numbering-driven heading levels nested into a SECTION tree behind a FRONT_MATTER title block (title/author/date/abstract roles); structured TABLE recovery (TABLE_STRUCTURE evidence preferred, deterministic line fallback) and EQUATION recovery (display chains, `(n)` numbers, raw-text fallback, `INLINE_EQUATION` marks); footnote reference recovery (`FOOTNOTE_OF` relations + additive `FOOTNOTE_REFERENCE` inline mark type); BIBLIOGRAPHY / BIBLIOGRAPHY_ENTRY / `CITATION` marks / `CITES` relations; region-derived stable node ids; `pdf_pipeline.sem_validate` post-recovery integrity audit wired into `semantic.issues`; render fallbacks so tables, equations, and bibliography entries never drop from the target PDF; new `paper-anatomy` Tier-1 exit-gate fixture plus a `semantic` expectation block on all 12 layout-truth files and `tests/benchmark/test_semantic_benchmark.py`.

### Fixed

- M2 walking skeleton exit gate: bundle reference validation and end-to-end artifact chain.
- M3 layout recovery review repairs: provenance on fused regions; page numbers and footnote markers excluded from primary flow; table caption projection; formula-shaped headings rejected; smoke golden updated after intentional heading and footer contract changes.
- M4 semantic recovery review repairs: `cross-page-paragraph` is a short-page single paragraph that paginates; layout gates require a cross-page CONTINUATION; citation hyphen/en-dash ranges expand; `FigureResource.embeddedImageIds` no longer stores PhysicalObjectIDs; SemanticValidator heading jumps use tree order; FOOTNOTE_REFERENCE recorded as a post-M2 freeze exception without a mass version bump.
- Evidence: mock provider formula density threshold lowered (0.25 → 0.15) so fragmented display math is recognizable; region text extraction widened to TABLE and FORMULA regions.
