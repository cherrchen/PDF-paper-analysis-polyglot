# Agent Note: 产品需求文档

Status: implemented

[中文](./2026-09-06-product-requirements.md) | [English](./2026-09-06-product-requirements.en.md)

## 问题

`docs/product/` 目录已预留为产品需求与 UX 笔记，但缺少面向最终用户的权威产品需求文档。架构、Schema 与 Milestone 缺少明确的上游产品约束来源。

## 决策

在 `docs/product/requirements.md` 建立 PRD v0.1（中文主文件），英文伴侣为 `requirements.en.md`。该文档定义产品目标、功能需求、非目标、验收标准与待确认问题；架构与开发文档应以其为上游约束，而非反向修改产品需求。`docs/product/README.md` 索引该文档；`docs/development/roadmap.md` 引用其为需求权威。

## 考虑过的替代方案

- 将 PRD 放在 `docs/architecture/`：会把产品需求与架构契约混在同一目录，违背一事一处。
- 仅以 Agent Note 承载：note 适合决策记录，不适合长篇、可独立阅读的产品需求真源。
- 仅中文、无英文伴侣：违反仓库双语文档约定。

## 后果

新增或变更产品行为时，应先对照 PRD v0.2 并更新需求文档。技术方案冲突时应重新审视技术方案。v0.1 建立记录见本目录；v0.2 闭合八项开放问题见 [产品需求文档 v0.2](./2026-09-06-product-requirements-v02.md)。
