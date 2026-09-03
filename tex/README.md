# TeX Live

LaTeX is a first-class Day 0 dependency. It is used for translated-paper reconstruction, PDF rendering, synthetic fixtures, and academic-style document generation.

## Supported environment

| Item | Value |
| --- | --- |
| Distribution | TeX Live 2026 |
| Default engine | LuaLaTeX |
| Build driver | latexmk |
| First-party package set | [`packages.txt`](packages.txt) |
| latexmk config | [`latexmkrc`](latexmkrc) |

XeLaTeX is allowed only where compatibility requires it. pdfLaTeX is not the primary renderer for multilingual project output.

Local development may use TeX Live, MacTeX, or another compatible TeX Live installation. `just doctor` verifies `lualatex` and `latexmk`. Docker is not required for local work.

CI installs a pinned TeX Live 2026 environment plus the package set in `packages.txt`.

Adding a TeX package is a dependency change: update `packages.txt` and explain the need. Do not rely on an undeclared full-TeX installation.

See `docs/development/latex.md` for setup, debugging, and warning policy.
