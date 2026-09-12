---
name: pdf-regression
description: Add or update PDF fixtures and golden SemanticDocument output.
---

# PDF regression

## When to use

A rendering or extraction bug needs a fixture, or golden output must change.

## Preconditions

Read `tests/AGENTS.md` and `docs/testing/golden.md`. Confirm the PDF/source license.

## Workflow

1. Identify the reproduction
2. Check license and origin; reject arbitrary copyrighted papers
3. Minimize the fixture
4. Add metadata under `tests/fixtures/metadata/`
5. Prefer LaTeX source over binary PDFs
6. For layout recovery, add `tests/fixtures/layout-truth/<name>.json`: keep `readingOrder` snippets and, after reviewing the PDF, freeze only correct `regions[]` (`pageIndex`, `LayoutLabel`, canonical `geometry`). Do not copy every recovered box. Uncertain regions stay out.
7. Add expected SemanticDocument output only when the extractor exists
8. Review the golden / benchmark-baseline diff; baseline updates follow `docs/testing/golden.md`
9. Run focused regression commands

## Validation

`just latex-smoke` for compile fixtures. Golden tests when defined.

## Failure handling

Never accept a new golden file blindly. Never update golden output merely to silence a failing test.

## Documentation impact

Explain why the fixture exists in its metadata `purpose` field.
