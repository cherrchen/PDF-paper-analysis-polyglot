# Workflow

[中文](./workflow.md) | [English](./workflow.en.md)

Trunk-based development on `main`. Feature branches: `feat/*`, `fix/*`, `refactor/*`, `docs/*`, `ci/*`, `chore/*`. There is no `develop` branch.

`main` stays releasable. Merge with squash. Conventional Commit PR titles.

Use `just` for all repository tasks. Lefthook runs staged checks on commit (including bilingual docs) and `just check-fast` on push.

Command ownership: [`.agents/notes/implemented/process/2026-09-03-canonical-repository-commands.md`](../../.agents/notes/implemented/process/2026-09-03-canonical-repository-commands.en.md).

Human docs pairing: [`bilingual.md`](bilingual.en.md). Development roadmap: [`roadmap.en.md`](roadmap.en.md).
