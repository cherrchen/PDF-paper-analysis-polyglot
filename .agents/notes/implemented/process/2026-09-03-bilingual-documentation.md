# Agent Note: 双语文档

Status: implemented

[中文](./2026-09-03-bilingual-documentation.md) | [English](./2026-09-03-bilingual-documentation.en.md)

## 问题

仓库落地页、当前态文档与 Agent Note 必须能用中文和英文阅读，又不能变成两套互相竞争的文档树。

## 决策

`README.md`、`AGENTS.md`、`docs/` 与 `.agents/notes/` 以中文为主。每个文件都有名为 `*.en.md` 的英文伴侣。两边都带含 `中文` 与 `English` 标签的跳转行。Skill 保持英文。`scripts/verify_bilingual_docs.py` 是配对校验器，由 `just docs-bilingual`、`just docs-fast`、Lefthook 与 CI 运行。

## 考虑过的替代方案

- 以英文为主、用 `*.zh.md` 作伴侣，会把中文藏在 GitHub 默认 README 之后。
- 并行的 `docs/zh/` 与 `docs/en/` 会复制路径并打断相对链接。
- 翻译 Skill 会要求 skill 校验器再维护一套标题词表。

## 后果

文档与 Agent Note 的修改必须两种语言一起交付。Vale 仍只检查英文，并跳过中文主文件。当前态责任文档：[`docs/development/bilingual.md`](../../../../docs/development/bilingual.md)。
