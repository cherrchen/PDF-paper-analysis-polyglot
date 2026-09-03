---
name: archive-agent-notes
description: Archive a fully superseded implemented Agent Note without destroying rationale.
---

# Archive Agent Notes

## When to use

An implemented decision is fully superseded and should no longer be current authority.

## Preconditions

Only implemented notes may be archived. A replacement implemented note must already exist.

## Workflow

1. Copy unique rationale and alternatives into the replacement if they would otherwise be lost
2. Move both the Chinese primary and English companion to `.agents/notes/archived/<class>/` without editing the bodies
3. Point current docs at the replacement
4. Do not later reformat or translate the archived files

## Validation

`uv run python scripts/verify_agent_notes.py` and `uv run python scripts/verify_bilingual_docs.py`

## Failure handling

If the old note is still partially in force, keep it implemented and cross-link instead of archiving.

## Documentation impact

Current-state docs must not cite archived notes as authority.
