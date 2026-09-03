# Agent standing orders

[中文](./AGENTS.md) | [English](./AGENTS.en.md)

Short rules for every session. Details live in linked owners.

## Mission

Build a maintainable PDF paper analysis system: ingest PDFs, recover structure, translate, reconstruct, and render through LaTeX / LuaLaTeX.

## Canonical commands

Use `just` as the repository command interface. Git hooks, CI, docs, and Agents call the same recipes.

See the `justfile`. Do not duplicate command logic in GitHub Actions, `package.json`, or this file.

## Repository map

Applications: `apps/`. Reusable Python: `packages/python/`. Reusable TypeScript: `packages/typescript/`. Rust: `crates/`. Contracts: `schemas/`. LaTeX templates: `templates/latex/`. Tests: `tests/`. Decisions: `.agents/notes/`. Skills: `.agents/skills/`.

Do not duplicate reusable business logic across applications.

## Architecture

Read current docs in `docs/architecture/` before architectural changes. Durable docs describe current reality. History belongs in Agent Notes.

Cross-language contracts belong in `schemas/`. Do not maintain independent authoritative SemanticDocument models in Python, TypeScript, or Rust.

## Generated code

Generated code has one source, one deterministic generator, is never edited by hand, and has CI freshness checks (`just generate-check`).

## Testing

Never update golden output merely to make tests pass. Follow `docs/testing/golden.md` and `.agents/skills/pdf-regression/SKILL.md`.

## LaTeX

LaTeX / LuaLaTeX is the initial canonical rendering backend. Do not introduce Typst or a generic multi-renderer architecture without an Agent Note. Do not treat generated LaTeX as semantic truth.

## Documentation

One fact, one authoritative home. README, `docs/`, and Agent Notes are Chinese-primary with English `*.en.md` companions. Follow [`docs/development/bilingual.md`](docs/development/bilingual.en.md). Update current-state docs together with code.

## Agent Notes

Every non-trivial behavior, architecture, contract, process, or testing change must add or update an Agent Note. Search active notes first. Do not silently rewrite an implemented decision. Archived notes are historical and non-authoritative.

## Security

Never commit credentials. Follow `SECURITY.md`.

## PRs

Use Conventional Commits. Complete `.github/PULL_REQUEST_TEMPLATE.md`. Run relevant `just` checks before finishing.

## Subtree instructions

- [`docs/AGENTS.md`](docs/AGENTS.en.md)
- [`packages/python/AGENTS.md`](packages/python/AGENTS.md)
- [`packages/typescript/AGENTS.md`](packages/typescript/AGENTS.md)
- [`crates/AGENTS.md`](crates/AGENTS.md)
- [`schemas/AGENTS.md`](schemas/AGENTS.md)
- [`templates/latex/AGENTS.md`](templates/latex/AGENTS.md)
- [`tests/AGENTS.md`](tests/AGENTS.md)
- [`.agents/notes/AGENTS.md`](.agents/notes/AGENTS.en.md)
