# Agent Note: Source mapping identity model

Status: proposed

[中文](./2026-09-03-source-mapping-identity-model.md) | [English](./2026-09-03-source-mapping-identity-model.en.md)

## Problem

Translation and reconstruction need stable relations among original PDF, SemanticDocument, and rendered PDF.

## Proposal

Design identity and mapping rules (page space, reading order, span IDs, citation anchors) before implementing them. Persist mappings as first-class SemanticDocument data, not as LaTeX comments.

## Alternatives considered

- Implicit order-only mapping will break on layout changes.
- Encoding mapping only in generated LaTeX couples semantics to a renderer.

## Acceptance criteria

- A documented coordinate system
- Stable IDs across extraction and render
- Tests for at least one multi-element fixture

## Risks

Unstable IDs will invalidate golden files and translation memory.
