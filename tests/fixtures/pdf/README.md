# PDF regression corpus

Source-controlled synthetic LaTeX fixtures. PDFs are produced by `just latex-smoke` into `tests/fixtures/source/latex/build/` and are not committed unless they are an intentional tracked baseline.

See `docs/testing/fixtures.md`.

## Tier 1 synthetic corpus

| Fixture | Source | Metadata | Covers |
| --- | --- | --- | --- |
| `smoke` | `source/latex/smoke.tex` | `metadata/smoke.yaml` | Single column, minimal baseline |
| `two-column` | `source/latex/two-column.tex` | `metadata/two-column.yaml` | Two-column layout |
| `spanning-figure` | `source/latex/spanning-figure.tex` | `metadata/spanning-figure.yaml` | Cross-column figure |
| `table-heavy` | `source/latex/table-heavy.tex` | `metadata/table-heavy.yaml` | Table + caption |
| `equation-heavy` | `source/latex/equation-heavy.tex` | `metadata/equation-heavy.yaml` | Inline + display equations |
| `footnote-multicolumn` | `source/latex/footnote-multicolumn.tex` | `metadata/footnote-multicolumn.yaml` | Footnotes in two columns |
| `bibliography` | `source/latex/bibliography.tex` | `metadata/bibliography.yaml` | Citations + bibliography |
| `cross-page-paragraph` | `source/latex/cross-page-paragraph.tex` | `metadata/cross-page-paragraph.yaml` | Cross-page paragraph |
| `mixed-bands` | `source/latex/mixed-bands.tex` | `metadata/mixed-bands.yaml` | Full-width bands + columns |
| `tikz-vector` | `source/latex/tikz-vector.tex` | `metadata/tikz-vector.yaml` | Vector figure (TikZ) |

## Tier 4 external

| Fixture | Metadata | Notes |
| --- | --- | --- |
| scanned PDFs | `metadata/scanned-external.yaml` | Manual/external only; not committed |
