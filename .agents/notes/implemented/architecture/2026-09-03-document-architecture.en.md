# Agent Note: Document Architecture v0.1

Status: implemented

[中文](./2026-09-03-document-architecture.md) | [English](./2026-09-03-document-architecture.en.md)

## Problem

Parser, renderer, viewer, and translation need a shared frozen document architecture contract. Related design was scattered across proposed Agent Notes and placeholder architecture pages, with no single authoritative baseline.

## Decision

Freeze **Document Architecture v0.1** as the cross-layer contract baseline. Authoritative document:

- [`docs/architecture/document-architecture.en.md`](../../../../docs/architecture/document-architecture.en.md)

Decision summary:

- Four independent layers: `PhysicalDocument`, `LayoutDocument`, `SemanticDocument`, `RenderDocument`
- Aggregate root `DocumentBundle` with mappings, derived layers, renders, provenance, and issues
- Third-party parsers produce Evidence only; they do not define Layout / Semantic models directly
- `RenderComposer` (formerly LayoutPlanner) generates Render IR from Semantic + Translation + Profile + Policy
- LaTeX Backend consumes Render IR only
- Capability Registry defines PDFium / MinerU / Docling / GROBID / internal responsibility boundaries
- Schema first: JSON Schema is the cross-language contract source of truth

This decision partially supersedes the following proposed notes (historical rationale preserved; no longer current authority):

- [`.agents/notes/proposed/architecture/2026-09-03-semantic-document-canonical-model.en.md`](../../proposed/architecture/2026-09-03-semantic-document-canonical-model.en.md)
- [`.agents/notes/proposed/architecture/2026-09-03-source-mapping-identity-model.en.md`](../../proposed/architecture/2026-09-03-source-mapping-identity-model.en.md)
- [`.agents/notes/proposed/architecture/2026-09-03-layout-reconstruction-pipeline.en.md`](../../proposed/architecture/2026-09-03-layout-reconstruction-pipeline.en.md)
- [`.agents/notes/proposed/architecture/2026-09-03-latex-render-model.en.md`](../../proposed/architecture/2026-09-03-latex-render-model.en.md)
- [`.agents/notes/proposed/architecture/2026-09-03-python-rust-performance-boundary.en.md`](../../proposed/architecture/2026-09-03-python-rust-performance-boundary.en.md)

Compatible with the implemented note [LaTeX as initial rendering backend](./2026-09-03-latex-as-initial-rendering-backend.en.md): v0.1 refines the path to RenderDocument → LaTeX without changing LaTeX as the sole first-class backend.

## Alternatives considered

- Keep design in scattered proposed Agent Notes: blocks parallel parser / schema work.
- Skip architecture freeze and write parser adapters first: risks wrong boundaries (especially Evidence vs Document).
- Use a single parser output as SemanticDocument source of truth: violates the evidence-provider principle.

## Consequences

- Architecture subpages (overview, pipeline, pdf-ingestion, source-mapping, semantic-document, rendering) link to `document-architecture.md` instead of marking topics as intentionally unresolved.
- Next engineering step: freeze five core schemas in `schemas/` (Physical, Layout, Semantic, Mapping, Evidence), then implement package APIs and parser adapters.
- New parsers, rendering backends, or layer boundary changes require a new Agent Note and an update to the v0.1 document or a v0.2 release.
