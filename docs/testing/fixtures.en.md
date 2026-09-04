# Fixtures

[中文](./fixtures.md) | [English](./fixtures.en.md)

Commit synthetic, self-authored, public-domain, or explicitly redistributable documents only.

Prefer:

```text
LaTeX source → latexmk / LuaLaTeX → PDF
```

Each non-trivial fixture has metadata in `tests/fixtures/metadata/`. Corpus manifest: [`tests/fixtures/pdf/README.md`](../../tests/fixtures/pdf/README.md).

## Tier 1 synthetic corpus

The first ten Tier 1 benchmark documents live under `tests/fixtures/source/latex/`:

```text
smoke                  — single-column baseline
two-column             — standard two-column article
spanning-figure        — cross-column figure
table-heavy            — table
equation-heavy         — equations
footnote-multicolumn   — footnotes
bibliography           — bibliography
cross-page-paragraph   — cross-page paragraph
mixed-bands            — full-width bands + columns
tikz-vector            — vector figure (TikZ)
```

Tier 4 scanned PDFs are not committed; placeholder metadata: `tests/fixtures/metadata/scanned-external.yaml`.

Do not commit a huge PDF corpus. Git history must stay small.

Command: `just latex-smoke` (compiles all fixture sources).
