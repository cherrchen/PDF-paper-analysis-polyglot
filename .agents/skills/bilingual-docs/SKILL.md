---
name: bilingual-docs
description: Create or update Chinese-primary / English-companion README, Agent Notes, and docs with jump links, then validate the pairs.
---

# Bilingual docs

## When to use

Adding or changing `README.md`, `AGENTS.md`, anything under `docs/`, or Agent Notes under `.agents/notes/`.

## Preconditions

Read [`docs/development/bilingual.md`](../../../docs/development/bilingual.md). Search active Agent Notes before changing the pairing convention.

## Workflow

1. Treat the unsuffixed `.md` file as the Chinese primary.
2. Put the English translation in the sibling `*.en.md` file. Never invert this.
3. After the H1 (and `Status:` on Agent Notes), add a jump line that links both files and contains the labels `中文` and `English`:
   `[中文](./topic.md) | [English](./topic.en.md)`
4. Chinese Agent Notes use Chinese required headings. English companions use English required headings. Keep `Status:` machine-readable in both.
5. English companions should link to other English companions when those pairs exist.
6. Run `just docs-bilingual` (also part of `just docs-fast`, Lefthook pre-commit, and CI `just docs`).

## Validation

`uv run python scripts/verify_bilingual_docs.py` and `uv run python scripts/verify_agent_notes.py` must pass. Do not merge a Chinese change without its English companion, or the reverse.

## Failure handling

Do not delete the English file to silence the checker. Do not put English in the primary `.md`. Do not introduce a third filename scheme (`README.zh.md`, `docs/en/`, etc.) without a process Agent Note.

## Documentation impact

Convention owner is `docs/development/bilingual.md`. Process rationale is the bilingual-documentation Agent Note.
