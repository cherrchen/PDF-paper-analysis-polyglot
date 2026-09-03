# Setup

[中文](./setup.md) | [English](./setup.en.md)

```bash
mise install
just setup
just doctor
just check
```

`mise` pins Python 3.13.12, Node.js 24, pnpm, uv, Rust 1.98, just, lefthook, and repository quality tools.

LaTeX is required and is not installed by mise. Install TeX Live 2026 or MacTeX, including `lualatex`, `latexmk`, `chktex`, and `latexindent`. `just setup` and `just doctor` fail if those commands are missing.

Docker is not required for routine development.

Details: [`latex.md`](latex.en.md), [`workflow.md`](workflow.en.md).
