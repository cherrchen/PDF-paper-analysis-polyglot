# Agent Note: Canonical repository commands

Status: implemented

[中文](./2026-09-03-canonical-repository-commands.md) | [English](./2026-09-03-canonical-repository-commands.en.md)

## Problem

Developers, Git hooks, CI, documentation, and Coding Agents must not each invent a different way to format, lint, test, or compile.

## Decision

`just` is the canonical repository task interface. GitHub Actions, Lefthook, README, and AGENTS.md delegate to `just` recipes. Language package scripts exist only as thin wrappers where a workspace tool requires them. New documentation checks, including bilingual pairing, are added to the `justfile` first.

## Alternatives considered

- Documenting raw `uv` / `pnpm` / `cargo` commands as the primary interface would drift immediately.
- Make or a custom shell framework would duplicate what `just` already provides.
- Per-language `package.json` / `Makefile` owners would recreate the split this note prevents.

## Consequences

New quality checks are added to the `justfile` first, then hooked from CI and Lefthook. Command semantics live in the `justfile`, not in copied documentation. `just generate` Ruff-formats the Pydantic binding after writing it, so `just generate-check` and `just fmt` agree on generated output.
