# 环境

[中文](./setup.md) | [English](./setup.en.md)

```bash
mise install
just setup
just doctor
just check
```

`mise` 固定 Python 3.13.12、Node.js 24、pnpm、uv、Rust 1.98、just、lefthook 以及仓库质量工具。

LaTeX 是必需的，且不由 mise 安装。请安装 TeX Live 2026 或 MacTeX，包含 `lualatex`、`latexmk`、`chktex` 与 `latexindent`。缺少这些命令时，`just setup` 与 `just doctor` 会失败。

日常开发不需要 Docker。

细节：[`latex.md`](latex.md)、[`workflow.md`](workflow.md)。
