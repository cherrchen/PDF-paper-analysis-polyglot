# SemanticDocument

[中文](./semantic-document.md) | [English](./semantic-document.en.md)

语义模型定义见 [`document-architecture.md`](document-architecture.md) 第 13–17 节。

契约真源位置（待实现）：`schemas/semantic-document/` 及关联的 physical、layout、mapping、evidence schema。

要点：

- 树 + 图：`SemanticNode` parent-child，`SemanticRelation` 表达 caption、citation、footnote 等
- Section 与 Heading 独立
- 块语义 → `SemanticNode`；行内语义 → `RichText` marks
- 禁止 page、bbox、column、font size 等版面信息

见已落地 note [`.agents/notes/implemented/architecture/2026-09-03-document-architecture.md`](../../.agents/notes/implemented/architecture/2026-09-03-document-architecture.md)。

语言包在 schema 落地后持有便利类型，不是独立真源。
