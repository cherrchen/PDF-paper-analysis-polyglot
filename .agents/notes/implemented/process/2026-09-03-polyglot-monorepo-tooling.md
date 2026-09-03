# Agent Note: 多语言单仓工具链

Status: implemented

[中文](./2026-09-03-polyglot-monorepo-tooling.md) | [English](./2026-09-03-polyglot-monorepo-tooling.en.md)

## 问题

仓库必须同时支持 Python、TypeScript、Rust 与 LaTeX，又不能让每个生态变成互不相连的工具链。

## 决策

mise 钉死运行时与开发工具。语言生态保留原生包管理器：uv、pnpm 与 Cargo。LaTeX 使用 TeX Live 加 latexmk。提交 lockfile。日常本地开发不需要 Docker。

## 考虑过的替代方案

- 只用语言原生版本文件（`.python-version`、`nvmrc`）会分裂开发者界面。
- 以 Nix 作为唯一工具链会抬高学生维护仓库的贡献门槛。
- 强制所有开发使用 Docker 会掩盖原生 TeX 与编辑器工作流。

## 后果

`mise install` 是第一步。CI 安装同一套 mise 工具。LaTeX 仍是由 `just doctor` 校验的外部 TeX Live 安装。
