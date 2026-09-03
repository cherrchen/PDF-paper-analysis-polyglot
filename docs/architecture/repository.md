# 仓库布局

[中文](./repository.md) | [English](./repository.en.md)

| 路径 | 角色 |
| --- | --- |
| `apps/` | 部署 / 运行时入口 |
| `packages/python/` | 可复用 Python |
| `packages/typescript/` | 可复用 TypeScript |
| `crates/` | 可复用 Rust |
| `schemas/` | 共享契约真源 |
| `templates/latex/` | 一等 LaTeX 模板 |
| `tex/` | TeX Live 宏包清单与 latexmk |
| `tests/` | 夹具、golden、集成、端到端 |
| `benchmarks/` | 性能测量 |
| `docs/` | 当前态文档 |
| `.agents/notes/` | 决策记录 |
| `.agents/skills/` | 可复用 Agent 流程 |
| `scripts/` | 由 `just` 调用的仓库自有校验器 |

应用不得长出隐藏库，例如 `apps/api/common/`。共享代码提升到有主的包中。
