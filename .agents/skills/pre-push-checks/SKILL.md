---
name: pre-push-checks
description: Map changed surfaces to just recipes before push or PR.
---

# Pre-push checks

## When to use

Before `git push`, after a focused change, or when deciding whether full CI is needed.

## Preconditions

Identify changed paths. Do not default to full `just ci` for a one-line docs fix if `just docs-fast` covers it. Do not skip required owners.

## Workflow

1. Python (`apps/api`, `apps/worker`, `packages/python`, `pyproject.toml`, `uv.lock`) → `just lint-python`, `just typecheck-python`, `just test-python`
2. TypeScript (`apps/web`, `packages/typescript`, `pnpm-lock.yaml`) → `just lint-ts`, `just typecheck-ts`, `just test-ts`
3. Rust (`crates`, `Cargo.*`) → `just lint-rust`, `just test-rust`
4. LaTeX (`templates/latex`, `tex`, fixtures) → `just latex-check`, `just latex-smoke`
5. Schemas → `just schema` plus language checks
6. Docs / Agent Notes → `just docs-fast` (includes bilingual pairing)
7. Mixed or workflow changes → `just check-fast`

## Validation

The selected `just` recipes pass.

## Failure handling

Do not ignore hook failures. Do not expand pre-commit into full pytest or Playwright.

## Documentation impact

None unless command semantics change; then update the `justfile` owner note.
