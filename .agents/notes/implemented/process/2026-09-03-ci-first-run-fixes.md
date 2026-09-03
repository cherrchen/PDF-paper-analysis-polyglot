# Agent Note: 首次 CI 闸门修复

Status: implemented

[中文](./2026-09-03-ci-first-run-fixes.md) | [English](./2026-09-03-ci-first-run-fixes.en.md)

## 问题

第一次推送的 `CI / gate` 在 LaTeX、文档与安全作业上失败，尽管 Python、TypeScript 与 Rust 已通过。

## 决策

TeX Live 2026 的 tlmgr 没有独立 `array` 包（它在 `tools` 里）；CI 宏包清单改为安装 `chktex` 与 `latexindent`。Vale 使用项目词表，避免把工具名当成拼写错误。所有 `actions/checkout` 设置 `persist-credentials: false`。同仓可复用 workflow 使用 `$/` 自引用语法。

## 考虑过的替代方案

- 把 Vale 或 zizmor 降到 warning-only 会藏起真问题。
- 继续列出 `array` 会让 `zauguin/install-texlive` 在 TeX Live 2026 上失败。

## 后果

文档与 workflow 的后续变更必须同时满足 Vale 词表与 zizmor 的 checkout 规则。CI LaTeX 作业额外安装 latexindent 所需的 Debian Perl 包。
