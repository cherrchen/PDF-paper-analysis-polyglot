# Repository layout

[中文](./repository.md) | [English](./repository.en.md)

| Path | Role |
| --- | --- |
| `apps/` | deployment/runtime entry points |
| `packages/python/` | reusable Python |
| `packages/typescript/` | reusable TypeScript |
| `crates/` | reusable Rust |
| `schemas/` | canonical shared contracts |
| `templates/latex/` | first-party LaTeX templates |
| `tex/` | TeX Live package set and latexmk |
| `tests/` | fixtures, golden, integration, e2e |
| `benchmarks/` | performance measurements |
| `docs/` | current-state documentation |
| `.agents/notes/` | decision records |
| `.agents/skills/` | reusable Agent workflows |
| `scripts/` | repository-owned validators used by `just` |

Applications must not grow hidden libraries such as `apps/api/common/`. Promote shared code into an owned package.
