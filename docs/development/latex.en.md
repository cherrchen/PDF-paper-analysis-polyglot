# LaTeX

[中文](./latex.md) | [English](./latex.en.md)

## Current policy

| Item | Value |
| --- | --- |
| Distribution | TeX Live 2026 |
| Default engine | LuaLaTeX |
| Driver | latexmk via `tex/latexmkrc` |
| Package set | `tex/packages.txt` (includes `luatexja`, `fandol`, `caption`, `multirow`) |
| Templates | `templates/latex/` |

XeLaTeX is allowed only for a documented compatibility need. pdfLaTeX is not the multilingual renderer.

## Local install

macOS: MacTeX 2026 (`brew install --cask mactex-no-gui`) or a full TeX Live 2026 tree.

Linux: TeX Live 2026 from TUG, then `tlmgr` to match `tex/packages.txt`.

`just doctor` must see `lualatex`, `latexmk`, `chktex`, and `latexindent`. Missing LaTeX is a hard failure.

## CI

CI installs pinned TeX Live 2026 plus `tex/packages.txt`. Docker is not required locally.

## Warning policy

Fatal errors fail the build (`-halt-on-error`). Missing required packages fail the build. Expected PDF missing fails the build.

First-party templates must not accumulate unexplained warnings. Third-party academic templates may emit benign layout warnings; do not globally disable ChkTeX to hide them.

## Debugging

1. Read the `.log` under the `build/` directory next to the source.
2. Re-run `just latex-smoke`.
3. Fix the template or undeclared package. Do not silence errors by weakening repository checks.

## TeX Live upgrades

Bump the documented year, update CI `texlive_version`, refresh `tex/packages.txt`, and record the change in an Agent Note. Renovate does not manage TeX packages.
