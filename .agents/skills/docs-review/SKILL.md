---
name: docs-review
description: Review documentation for one-fact-one-home and current-state accuracy.
---

# Docs review

## When to use

Any change to `docs/`, `README.md`, `AGENTS.md`, or Agent Notes.

## Preconditions

Read `docs/AGENTS.md` and `docs/development/bilingual.md`. Distinguish current-state docs from notes and postmortems.

## Workflow

1. Confirm the change updates the single owner document in both languages
2. Follow `.agents/skills/bilingual-docs/SKILL.md` for README, `docs/`, and Agent Notes
3. Remove copied rationale that belongs in Agent Notes
4. Reject future tense presented as current architecture
5. Run `just docs-fast`

## Validation

Markdown, bilingual pairing, Agent Note, and Skill validators pass.

## Failure handling

Do not disable Vale or markdownlint globally.

## Documentation impact

This skill is the procedure; architecture truth stays in `docs/architecture/`.
