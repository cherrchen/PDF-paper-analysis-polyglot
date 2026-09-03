---
name: agent-note
description: Create or update an Agent Note using the lifecycle and class taxonomy.
---

# Agent Note

## When to use

Any non-trivial behavior, architecture, contract, process, or testing change.

## Preconditions

Search `.agents/notes/proposed`, `implemented`, and `rejected`. Read `.agents/notes/AGENTS.md`.

## Workflow

1. Classify fact update vs new decision
2. Choose lifecycle and class from the closed sets
3. Name the Chinese primary `yyyy-mm-dd-topic-title.md` and the English companion `yyyy-mm-dd-topic-title.en.md`
4. Use Chinese required headings in the primary and English required headings in the companion. Keep `Status:` in both.
5. Add the language jump line. Follow `.agents/skills/bilingual-docs/SKILL.md`.
6. Link related notes with relative paths (same language)
7. Update current-state docs in both languages if behavior shipped

## Validation

`uv run python scripts/verify_agent_notes.py` and `uv run python scripts/verify_bilingual_docs.py`

## Failure handling

Do not invent new classes. Do not rewrite an implemented note into its opposite.

## Documentation impact

Implemented notes must match `docs/` current reality.
