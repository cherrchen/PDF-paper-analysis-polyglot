# Bilingual documentation

[中文](./bilingual.md) | [English](./bilingual.en.md)

Chinese is the primary language for repository landing docs. English is a companion, not a second source of truth.

## Scope

Paired files:

- `README.md` / `README.en.md`
- `AGENTS.md` / `AGENTS.en.md`
- every markdown file under `docs/`
- every markdown file under `.agents/notes/`

Not paired: Skills (`SKILL.md` stays English because validators require English section names), package READMEs, subtree `AGENTS.md` outside `docs/` and `.agents/notes/`, `CONTRIBUTING.md`, `SECURITY.md`, and `CHANGELOG.md`.

## Filenames

| Role | Pattern |
| --- | --- |
| Chinese primary | unsuffixed `*.md` |
| English companion | sibling `*.en.md` |

Do not introduce `*.zh.md`, `docs/en/`, or inverted primaries.

## Jump links

After the H1 (and after `Status:` on Agent Notes), both files include:

```markdown
[中文](./topic.md) | [English](./topic.en.md)
```

The labels `中文` and `English` are required. English companions should link to other English companions when those pairs exist. Chinese primaries should link to other Chinese primaries.

## Agent Notes

`Status:` stays English and machine-readable in both files. Chinese primaries use Chinese required headings. English companions use English required headings. Implemented Chinese notes must not keep `## 提案`.

## Checks

`just docs-bilingual` (also part of `just docs-fast`, Lefthook pre-commit, and CI `just docs`) requires every scoped file to have a counterpart and a jump link. Procedure: [`.agents/skills/bilingual-docs/SKILL.md`](../../.agents/skills/bilingual-docs/SKILL.md). Decision: [`.agents/notes/implemented/process/2026-09-03-bilingual-documentation.md`](../../.agents/notes/implemented/process/2026-09-03-bilingual-documentation.en.md).
