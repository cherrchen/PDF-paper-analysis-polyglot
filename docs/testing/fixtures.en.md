# Fixtures

[中文](./fixtures.md) | [English](./fixtures.en.md)

Commit synthetic, self-authored, public-domain, or explicitly redistributable documents only.

Prefer:

```text
LaTeX source → latexmk / LuaLaTeX → PDF
```

Each non-trivial fixture has metadata in `tests/fixtures/metadata/`. Corpus manifest: [`tests/fixtures/pdf/README.md`](../../tests/fixtures/pdf/README.md).

## Tier 1 synthetic corpus

The Tier 1 benchmark corpus (12 documents) lives under `tests/fixtures/source/latex/`:

```text
smoke                  — single-column baseline
two-column             — standard two-column article
spanning-figure        — cross-column figure
table-heavy            — table
equation-heavy         — equations
footnote-multicolumn   — footnotes
bibliography           — bibliography
cross-page-paragraph   — cross-page paragraph (short page, one paragraph that paginates)
mixed-bands            — full-width bands + columns
tikz-vector            — vector figure (TikZ)
figure-caption         — raster figure with caption
paper-anatomy          — composite paper anatomy (M4 exit gate: title block, abstract, nested sections, figure, table, numbered equation, footnote, bibliography + citations)
```

Tier 4 scanned PDFs are not committed; placeholder metadata: `tests/fixtures/metadata/scanned-external.yaml`.

Do not commit a huge PDF corpus. Git history must stay small.

Command: `just latex-smoke` (compiles all fixture sources). Generated PDFs are not committed. Tests that need those PDFs `pytest.skip` when the files are missing instead of crashing. The GitHub Python job compiles fixtures before `just test-python`, so pipeline, golden, and coverage gates still run on a clean checkout.
