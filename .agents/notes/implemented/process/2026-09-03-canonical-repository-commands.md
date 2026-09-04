# Agent Note: 仓库规范命令

Status: implemented

[中文](./2026-09-03-canonical-repository-commands.md) | [English](./2026-09-03-canonical-repository-commands.en.md)

## 问题

开发者、Git hooks、CI、文档与 Coding Agent 不得各自发明一套格式化、lint、测试或编译方式。

## 决策

`just` 是规范的仓库任务界面。GitHub Actions、Lefthook、README 与 AGENTS.md 都委托给 `just` recipe。语言包脚本仅在工作区工具要求时作为薄封装存在。包括双语配对在内的新文档检查，先加到 `justfile`。

## 考虑过的替代方案

- 把原始 `uv` / `pnpm` / `cargo` 命令写成主界面会立刻漂移。
- Make 或自研 shell 框架会重复 `just` 已提供的能力。
- 按语言拆开的 `package.json` / `Makefile` 责任人会重新制造本 note 要防止的分裂。

## 后果

新质量检查先写入 `justfile`，再挂到 CI 与 Lefthook。命令语义活在 `justfile` 中，而不是复制粘贴的文档里。`just generate` 在写出 Pydantic 绑定后运行 Ruff format，因此 `just generate-check` 与 `just fmt` 对生成物的看法一致。
