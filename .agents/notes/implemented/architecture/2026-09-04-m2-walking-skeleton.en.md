# Agent Note: M2 Walking Skeleton end-to-end pipeline

Status: implemented

[中文](./2026-09-04-m2-walking-skeleton.md) | [English](./2026-09-04-m2-walking-skeleton.en.md)

> The 2026-09-05 review reopened the M2 exit gate, which passed again after repairs. This note preserves the original implementation and rationale; see the [M2 review repair note](../bug-fix/2026-09-05-m2-review-repairs.en.md) for the corrected contracts and validation results.

## Problem

M1 froze the five canonical schemas, but all product code was still stubs: no PDF ingestion, no recovery pipeline, no rendering, no viewer. M2 (Walking Skeleton) demanded the first true end-to-end loop — deliberately low parsing quality, real architecture validation.

## Decision

All seven phases are complete. Pipeline and artifacts:

1. **PDFium selection (before Phase 2.1)**: PDFium is accessed via `pypdfium2` (4.30, Apache-2.0/BSD dual-licensed bindings over Google PDFium's BSD-style license), added as a dependency of `packages/python/pdf-pipeline`. Per [Python / Rust performance boundary](../../proposed/architecture/2026-09-03-python-rust-performance-boundary.en.md), orchestration and extraction stay in Python until a measured hotspot says otherwise.
2. **Physical backend (2.1)**: `pdf_pipeline.physical.extract_physical_document` extracts Pages / TextSpans / ImageObjects / Geometry from PDF bytes into canonical page space (origin top-left, y down) and emits a validated `PhysicalDocument`. Line fragments merge into spans by vertical overlap plus horizontal gap. **Determinism**: IDs derive from `pdf_pipeline.ids.stable_uuid` (source fingerprint + stable counters), so parsing the same PDF bytes twice yields byte-identical documents (the requirement Roadmap 1.2 deferred to M2.1).
3. **Minimal layout (2.2)**: `pdf_pipeline.layout.recover_layout_document` produces only TEXT / FIGURE regions plus HEADING_LIKE labels (median font-size ratio heuristic), one band per page, naive column detection (gutter measured from spans fully inside one page half), with ReadingFlowGraph as source of truth and a linear derived primaryFlow. Column detection was validated on BERT (ICLR two-column, 16/16 pages) and Attention (NeurIPS single-column).
4. **Minimal semantic recovery (2.3)**: `pdf_pipeline.semantic.recover_semantic_document` produces only HEADING / PARAGRAPH / FIGURE / FIGURE_CAPTION nodes (DOCUMENT root); the caption heuristic binds a short text region directly below and horizontally overlapping a figure, linked by a CAPTION_OF relation. The semantic layer carries zero geometry; `validate_layer_separation` and `validate_bundle_references` stay clean.
5. **Dummy translation (2.4)**: `paper_llm.translation` provides `DummyTranslationProvider` (`[TRANSLATED]` prefix) and `translate_document`. Identity verification: node ids, relations, and tree shape survive translation; only text-node content changes.
6. **LaTeX renderer (2.5)**: `templates/latex/generic-academic.tex` (heading/paragraph/figure/caption) plus the `pdf_pipeline.render_latex` projection. Per the [LaTeX render model](../../proposed/architecture/2026-09-03-latex-render-model.en.md): template owns presentation, projection owns structure, TeX never enters SemanticDocument, single backend with no Renderer trait.
7. **RenderAnchor (2.6)**: the projection emits `\renderanchor{<nodeId>}` (a hyperref hypertarget) per node; after compilation `pdf_pipeline.render_anchor.recover_render_anchors` reads the named destinations back through PDFium (UTF-16LE name decoding) and records target page + coordinates as RenderBinding/RenderAnchor entries in the `MappingBundle`. Anchor id == SemanticNode id, establishing the three-way `SourceAnchor ↔ SemanticNode ↔ RenderAnchor` mapping. Y coordinates flip to canonical space by page height.
8. **Viewer (2.7)**: `apps/web` gains `pdfjs-dist` with Source/Target canvases; `pdf_pipeline.pipeline.run_pipeline` emits `viewer/data/` (source.pdf, target.pdf, mapping.json, viewer-meta.json) for static fetch. Playwright e2e (`tests/e2e/viewer-navigation.spec.ts`) locks mapping coverage and dual-canvas loading.
9. **Orchestration and regression**: `python -m pdf_pipeline run <input.pdf> <outdir>` runs the whole chain, writing five canonical JSON documents plus the target PDF and viewer data, then checks bundle reference integrity. End-to-end determinism verified: repeated runs produce byte-identical JSON. `tests/golden/smoke/semantic.json` is the golden SemanticDocument for the smoke fixture (established per `docs/testing/golden.md`).
10. **Phase 2.1 real-paper validation**: `packages/python/pdf-pipeline/tests/test_physical_external.py` (`slow` marker) downloads three public arXiv papers (Attention Is All You Need / BERT / GPT-3, cached under gitignored `tests/fixtures/external/papers/`) and asserts correct page counts, complete title/abstract text, and in-page text-span coordinates. Real PDFs may legitimately place images beyond the page (clipped at render time); the physical layer records them faithfully without clamping.

## Alternatives considered

- PyMuPDF: AGPL licensing conflicts with the repository's source-available non-commercial terms; PDFium's dual BSD does not.
- Rust `crates/pdf-core` backend: no measured hotspot, premature FFI cost, against the performance-boundary note.
- RenderAnchors via LaTeX comments or coordinate back-inference: the identity-model note requires mappings as first-class persisted data; comments do not survive reflow.
- Column detection via x-midpoint histograms: confused by page numbers, headers, and spanning titles; measuring the gutter from fully one-sided spans is stable.

## Consequences

- M2 Exit Gate achieved: PDF → Physical → Layout → Semantic → Translation → LaTeX → Target PDF → bidirectional navigation all hold, all five artifacts pass canonical validation and cross-layer checks, and the whole loop reproduces byte-for-byte.
- New dependencies: Python `pypdfium2` (pdf-pipeline), npm `pdfjs-dist` (apps/web). Pipeline-generated viewer data (`apps/web/public/data/`) and `tests/fixtures/external/` are gitignored.
- New fixture: `figure-caption` (`.tex` source + placeholder PNG + metadata), added to the Tier-1 table.
- Known limitations (deliberately left to M3+): crude caption/heading heuristics, one band per page, naive column detection, FigureContent without real resource ids, and viewer navigation currently verifying mapping data plus canvas loading (region-level click-to-jump can be enabled by overlaying render coordinates; the mapping data is already in place).
- Parsing quality work starts with M3 (Layout Recovery Engine); the layer boundaries and ID stability of this skeleton are the foundation for everything that follows.
