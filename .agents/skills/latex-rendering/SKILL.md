---
name: latex-rendering
description: Change LaTeX templates or projection code and validate compile output.
---

# LaTeX rendering

## When to use

Template, latexmk, TeX package, or LaTeX projection changes.

## Preconditions

Read `docs/architecture/rendering.md`, `templates/latex/AGENTS.md`, and the implemented LaTeX backend note.

## Workflow

1. Identify the owning template or projection layer
2. Modify first-party sources only as needed
3. Run `just latex-check`
4. Run `just latex-smoke`
5. Inspect logs for fatal errors and unexplained first-party warnings
6. Validate that the expected PDF exists under `build/`
7. Update fixtures or docs only when the contract changed

## Validation

Compile success, expected PDF produced, ChkTeX clean for first-party files.

## Failure handling

Do not silence LaTeX errors by disabling checks globally. Do not blindly delete unsupported content. Do not hardcode document-specific hacks into generic rendering code.

## Documentation impact

Engine or package-set changes update `docs/development/latex.md` and `tex/packages.txt`.
