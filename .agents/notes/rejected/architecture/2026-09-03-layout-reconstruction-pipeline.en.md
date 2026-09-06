# Agent Note: Layout reconstruction pipeline

Status: rejected — landed by later implemented notes; no longer current authority

[中文](./2026-09-03-layout-reconstruction-pipeline.md) | [English](./2026-09-03-layout-reconstruction-pipeline.en.md)

## Problem

Academic PDFs mix columns, figures, footnotes, and equations. The extraction-to-layout path is not chosen.

## Proposal

Treat layout reconstruction as an explicit pipeline stage that emits SemanticDocument, separate from rendering. Parser and OCR engines are selected only after a dependency Agent Note.

## Alternatives considered

- Rendering-driven reconstruction (inferring structure from LaTeX) inverts the architecture.
- A single opaque model call with no layout stage would block deterministic tests.

## Acceptance criteria

- Pipeline stages are named and testable
- Fixtures exist for at least single-column and math-heavy layouts
- Native PDF libraries are not added silently

## Risks

Choosing PDFium/MuPDF/Poppler without isolation will dominate builds and licenses.
