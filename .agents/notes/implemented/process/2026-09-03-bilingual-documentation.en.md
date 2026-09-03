# Agent Note: Bilingual documentation

Status: implemented

[中文](./2026-09-03-bilingual-documentation.md) | [English](./2026-09-03-bilingual-documentation.en.md)

## Problem

The repository landing page, current-state docs, and Agent Notes must be readable in Chinese and English without two competing documentation trees.

## Decision

Chinese is the primary language for `README.md`, `AGENTS.md`, `docs/`, and `.agents/notes/`. Each file has an English companion named `*.en.md`. Both files carry a jump line with the labels `中文` and `English`. Skills stay English. `scripts/verify_bilingual_docs.py` is the pairing checker and runs from `just docs-bilingual`, `just docs-fast`, Lefthook, and CI.

## Alternatives considered

- English-primary with `*.zh.md` companions would hide Chinese on GitHub's default README.
- Parallel `docs/zh/` and `docs/en/` trees would duplicate paths and break relative links.
- Translating Skills would require a second heading vocabulary in the skill validator.

## Consequences

Docs and Agent Note edits ship both languages together. Vale remains English-only and skips Chinese primaries. Current-state owner: [`docs/development/bilingual.md`](../../../../docs/development/bilingual.en.md).
