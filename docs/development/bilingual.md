# 双语文档

[中文](./bilingual.md) | [English](./bilingual.en.md)

仓库落地文档以中文为主。英文是伴侣，不是第二套真源。

## 范围

成对文件：

- `README.md` / `README.en.md`
- `AGENTS.md` / `AGENTS.en.md`
- `docs/` 下每一份 markdown
- `.agents/notes/` 下每一份 markdown

不成对：Skill（`SKILL.md` 保持英文，因为校验器要求英文小节名）、各包 README、`docs/` 与 `.agents/notes/` 之外的子树 `AGENTS.md`、`CONTRIBUTING.md`、`SECURITY.md`、`CHANGELOG.md`。

## 文件名

| 角色 | 模式 |
| --- | --- |
| 中文主文件 | 无后缀 `*.md` |
| 英文伴侣 | 同目录 `*.en.md` |

不要引入 `*.zh.md`、`docs/en/`，或把英文当成主文件。

## 跳转

H1 之后（Agent Note 还要在 `Status:` 之后），两个文件都包含：

```markdown
[中文](./topic.md) | [English](./topic.en.md)
```

必须出现标签 `中文` 和 `English`。英文伴侣应链到其他英文伴侣（若该对已存在）。中文主文件应链到其他中文主文件。

## Agent Note

两边的 `Status:` 都保持英文、可机读。中文主文件使用中文必填标题。英文伴侣使用英文必填标题。已落地的中文 note 不得保留 `## 提案`。

## 检查

`just docs-bilingual`（同时属于 `just docs-fast`、Lefthook pre-commit 与 CI `just docs`）要求范围内每个文件都有伴侣和跳转。流程：[`.agents/skills/bilingual-docs/SKILL.md`](../../.agents/skills/bilingual-docs/SKILL.md)。决策：[`.agents/notes/implemented/process/2026-09-03-bilingual-documentation.md`](../../.agents/notes/implemented/process/2026-09-03-bilingual-documentation.md)。
