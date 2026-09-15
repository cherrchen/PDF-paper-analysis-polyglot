# PDF Paper Analysis

[中文](./README.md) | [English](./README.en.md)

Polyglot monorepo for PDF paper analysis, document understanding, translation, structure reconstruction, and PDF rendering.

**Status:** M1–M3 complete; M4–M7 baselines have landed (including 1 Layout→N Semantic, structured tables, author-year citations, and the parser ensemble). M8 batches A, B, C, and D have landed (local workspace, local job orchestration, stage cache keys and invalidation, specialist failure isolation). M8 admission: the three PRD surfaces are implemented + synthetic-fixture passed; real parser tool output is not verified. v1 plan: [M8 admission and v1 development plan](docs/development/m8.en.md). See the [development roadmap](docs/development/roadmap.en.md) for current progress.

## Rendering

The current rendering backend is **LaTeX / LuaLaTeX**:

```text
SemanticDocument
      +
TranslationLayer
      ↓
RenderComposer
      ↓
RenderDocument
      ↓
LaTeX Backend
      ↓
LuaLaTeX
      ↓
PDF
```

LaTeX is a rendering representation. SemanticDocument remains the canonical semantic model; translated content and layout decisions belong to TranslationLayer and RenderDocument respectively.

## Repository map

| Path | Owner |
| --- | --- |
| `apps/` | runtime entry points (`web`, `api`, `worker`) |
| `packages/python/` | reusable Python |
| `packages/typescript/` | reusable TypeScript |
| `crates/` | performance-critical Rust |
| `schemas/` | canonical cross-language contracts |
| `templates/latex/` | first-party LaTeX templates |
| `tex/` | TeX Live package set and latexmk config |
| `tests/` | fixtures, golden, integration, e2e |
| `docs/` | current-state documentation |
| `.agents/` | Agent Notes and Skills |

Reusable logic does not belong inside applications.

## Quick setup

```bash
mise install
just setup
just doctor
just check
```

LaTeX (TeX Live 2026 / MacTeX, LuaLaTeX, latexmk) is required. `just setup` does not skip it.

## Canonical commands

Use `just`. Do not treat `uv`, `pnpm`, `cargo`, or `latexmk` as the primary developer interface.

| Command | Meaning |
| --- | --- |
| `just setup` | install workspaces and hooks |
| `just doctor` | verify toolchains |
| `just check-fast` | pre-push validation |
| `just check` | developer-complete validation |
| `just ci` | exhaustive checks |

Run `just --list` for the full interface.

## Documentation

- Architecture: [`docs/architecture/overview.md`](docs/architecture/overview.en.md)
- Development roadmap: [`docs/development/roadmap.md`](docs/development/roadmap.en.md)
- Setup: [`docs/development/setup.md`](docs/development/setup.en.md)
- Bilingual docs: [`docs/development/bilingual.md`](docs/development/bilingual.en.md)
- Testing: [`docs/testing/overview.md`](docs/testing/overview.en.md)
- Agent standing orders: [`AGENTS.md`](AGENTS.en.md)

## License

MIT License **plus Non-Commercial additional terms**. Personal, academic, educational, and research use is permitted. Commercial use is prohibited without a separate written license. See [`LICENSE`](LICENSE).

This is source-available. It is not unmodified OSI-approved MIT.
