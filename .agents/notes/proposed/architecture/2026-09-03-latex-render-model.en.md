# Agent Note: LaTeX render model

Status: proposed

[中文](./2026-09-03-latex-render-model.md) | [English](./2026-09-03-latex-render-model.en.md)

## Problem

SemanticDocument must be projected into LaTeX without leaking TeX commands into the semantic model.

## Proposal

Introduce a dedicated render-model / LaTeX projection layer between SemanticDocument and `templates/latex/`. Templates own presentation. Projection owns structure. Do not build a generic multi-renderer trait until a second backend is actually adopted.

## Alternatives considered

- String-building LaTeX inside SemanticDocument serializers would pollute the canonical model.
- A Renderer trait for one backend is speculative.

## Acceptance criteria

- Semantic types contain no TeX required fields except explicit raw-source captures
- First-party templates compile via `just latex-smoke`
- Projection changes have rendering tests

## Risks

Overfitting templates to one paper. Global ChkTeX suppressions hiding real errors.
