# Agent Note: Agent Note 生命周期

Status: implemented

[中文](./2026-09-03-agent-note-lifecycle.md) | [English](./2026-09-03-agent-note-lifecycle.en.md)

## 问题

架构理由必须活过提交说明与聊天记录，又不能再搞一套互相竞争的 ADR 系统。

## 决策

`.agents/notes/<lifecycle>/<class>/` 下的 Agent Note 是唯一的决策记录系统。生命周期为 proposed、implemented、rejected、archived。类别为 feature、bug-fix、simplification、architecture、process、testing。校验器作为 `just docs` 的一部分，强制目录树、文件名、状态、分语言标题、双语配对与链接。配对约定：[`.agents/notes/implemented/process/2026-09-03-bilingual-documentation.md`](2026-09-03-bilingual-documentation.md)。

## 考虑过的替代方案

- `docs/adr/` 外加聊天笔记会重复责任人。
- 没有校验器的自由 markdown 会腐烂。
- 只靠 Git 历史会藏起被否决的替代方案。

## 后果

非平凡的行为、架构、契约、流程与测试变更必须新增或更新 note。分类法变更需要 process note 以及校验器变更。
