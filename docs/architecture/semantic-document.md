# SemanticDocument

[中文](./semantic-document.md) | [English](./semantic-document.en.md)

语义模型定义见 [`document-architecture.md`](document-architecture.md) 第 13–17 节。

契约真源（已实现，M1）：`schemas/semantic-document/schema.json`（版本 `0.1.0`）。关联 schema：`schemas/common/`、`schemas/physical-document/`、`schemas/evidence/`、`schemas/layout-document/`、`schemas/mapping/`。

要点：

- 树 + 图：`SemanticNode` parent-child，`SemanticRelation` 表达 caption、citation、footnote 等
- Section 与 Heading 独立
- 块语义 → `SemanticNode`；行内语义 → `RichText` marks
- 禁止 page、bbox、column、font size 等版面信息；唯一开放位置是 `SemanticNode.attributes`，其中的嵌套对象也由 `document_model.validators.validate_layer_separation` 递归检查
- `EquationContent` 与公式 Evidence 必须至少保留 LaTeX、MathML、Unicode / raw text 或 source preview 中的一种表示，禁止无内容公式

见已落地 note [`.agents/notes/implemented/architecture/2026-09-04-m1-core-document-contracts.md`](../../.agents/notes/implemented/architecture/2026-09-04-m1-core-document-contracts.md)。

语言包在 schema 落地后持有便利类型，不是独立真源：Python 绑定在 `packages/python/document-model`（Pydantic，生成），TypeScript 绑定在 `packages/typescript/document-model`（生成类型 + 运行时 schema 校验器）。
