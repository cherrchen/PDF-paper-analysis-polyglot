# 架构决策

[中文](./README.md) | [English](./README.en.md)

本仓库采用 **Agent Note** 作为 Architecture Decision Record（ADR）载体，而不是独立的 `docs/decisions/*.md` 决策文件树。

## 在哪里找决策

| 状态 | 位置 |
| --- | --- |
| 已落地 | [`.agents/notes/implemented/`](../../.agents/notes/implemented/) |
| 提案中 | [`.agents/notes/proposed/`](../../.agents/notes/proposed/) |
| 已否决 | [`.agents/notes/rejected/`](../../.agents/notes/rejected/) |

生命周期与必填字段： [`.agents/notes/AGENTS.md`](../../.agents/notes/AGENTS.md)。

## 关键已落地架构决策

| 主题 | Agent Note |
| --- | --- |
| Document Architecture v0.1 | [`2026-09-03-document-architecture.md`](../../.agents/notes/implemented/architecture/2026-09-03-document-architecture.md) |
| LaTeX 初始渲染后端 | [`2026-09-03-latex-as-initial-rendering-backend.md`](../../.agents/notes/implemented/architecture/2026-09-03-latex-as-initial-rendering-backend.md) |
| 双语文档 | [`2026-09-03-bilingual-documentation.md`](../../.agents/notes/implemented/process/2026-09-03-bilingual-documentation.md) |
| 规范仓库命令 | [`2026-09-03-canonical-repository-commands.md`](../../.agents/notes/implemented/process/2026-09-03-canonical-repository-commands.md) |

## 何时写新 ADR

以下变更必须新增或更新 Agent Note（见 [`docs/development/roadmap.md`](../development/roadmap.md) §9）：

```text
新增核心 IR layer
修改 SemanticNode identity
修改 Anchor 架构
修改坐标系统
修改 Schema compatibility policy
更改 third-party parser ownership
引入新的 canonical backend
更改 Translation identity
修改 Render pipeline
```

## 当前态文档

给人看的架构当前态在 [`docs/architecture/`](../architecture/overview.md)。决策理由在 Agent Note；不要重复抄写。
