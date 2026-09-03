# Agent Note: LaTeX as initial rendering backend

Status: implemented

[中文](./2026-09-03-latex-as-initial-rendering-backend.md) | [English](./2026-09-03-latex-as-initial-rendering-backend.en.md)

## Problem

Reconstructed and translated papers must render to PDF with Unicode, multilingual, and mathematics support from day one.

## Decision

LaTeX is the only first-class rendering backend. LuaLaTeX is the default engine. latexmk drives compilation. First-party templates live in `templates/latex/`. SemanticDocument remains canonical; LaTeX is a projection. Typst is intentionally deferred and is not installed, templated, or advertised as a current capability.

## Alternatives considered

- Starting with a generic Renderer interface would be speculative.
- Making pdfLaTeX primary would fail Unicode and CJK requirements.
- Installing Typst during bootstrap would imply a second renderer that does not exist.

## Consequences

Rendering work follows `.agents/skills/latex-rendering/SKILL.md`. Introducing Typst or a dual-renderer design requires a proposed architecture Agent Note covering canonical renderer, mapping, equations, templates, and maintenance cost.
