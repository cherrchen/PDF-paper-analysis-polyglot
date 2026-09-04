# Architecture decisions

[中文](./README.md) | [English](./README.en.md)

This repository uses **Agent Notes** as Architecture Decision Record (ADR) carriers instead of a separate `docs/decisions/*.md` decision tree.

## Where to find decisions

| Status | Location |
| --- | --- |
| Implemented | [`.agents/notes/implemented/`](../../.agents/notes/implemented/) |
| Proposed | [`.agents/notes/proposed/`](../../.agents/notes/proposed/) |
| Rejected | [`.agents/notes/rejected/`](../../.agents/notes/rejected/) |

Lifecycle and required headings: [`.agents/notes/AGENTS.md`](../../.agents/notes/AGENTS.md).

## Key implemented architecture decisions

| Topic | Agent Note |
| --- | --- |
| Document Architecture v0.1 | [`2026-09-03-document-architecture.en.md`](../../.agents/notes/implemented/architecture/2026-09-03-document-architecture.en.md) |
| LaTeX as initial rendering backend | [`2026-09-03-latex-as-initial-rendering-backend.en.md`](../../.agents/notes/implemented/architecture/2026-09-03-latex-as-initial-rendering-backend.en.md) |
| Bilingual documentation | [`2026-09-03-bilingual-documentation.en.md`](../../.agents/notes/implemented/process/2026-09-03-bilingual-documentation.en.md) |
| Canonical repository commands | [`2026-09-03-canonical-repository-commands.en.md`](../../.agents/notes/implemented/process/2026-09-03-canonical-repository-commands.en.md) |

## When to write a new ADR

These changes require a new or updated Agent Note (see [`docs/development/roadmap.en.md`](../development/roadmap.en.md) §9):

```text
New core IR layer
SemanticNode identity change
Anchor architecture change
Coordinate system change
Schema compatibility policy change
Third-party parser ownership change
New canonical backend
Translation identity change
Render pipeline change
```

## Current-state documentation

Human-facing architecture current state: [`docs/architecture/`](../architecture/overview.en.md). Decision rationale lives in Agent Notes; do not duplicate it here.
