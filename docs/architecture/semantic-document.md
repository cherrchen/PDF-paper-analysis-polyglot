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

M4 恢复引擎（`pdf_pipeline.semantic` + `sem_*` 模块）的产出形态：

- DOCUMENT root 首子为 FRONT_MATTER，其下是编号驱动的 SECTION 树；HEADING level 来自标题文本 pattern
- 段落合并消费 CONTINUATION 边；`attributes.layoutRegionIds` 驱动 N Layout → 1 Semantic 的多 fragment SourceAnchor。1 Layout → N Semantic 尚未实现
- 行内 marks：`CITATION` / `FOOTNOTE_REFERENCE` / `INLINE_EQUATION`
- 识别失败不丢内容：TABLE 默认行 fallback；EQUATION 保留 rawText；未解析引用保留文本并以 Issue 记录。`FigureResource.embeddedImageIds` 保持空直到 ResourceStore
- 每个节点与关系带恢复 `ProvenanceRecord`（producer / version / operation / layout region 与 fusion 输入）
- 恢复后由 `pdf_pipeline.sem_validate` 按文档树序审计（含环与父子一致性），结果写入 `SemanticDocument.issues`
- 落地决策：[M4 Semantic Recovery Engine](../../.agents/notes/implemented/architecture/2026-09-06-m4-semantic-recovery-engine.md)；审查修复：[M4 Review 修复](../../.agents/notes/implemented/bug-fix/2026-09-06-m4-review-repairs.md)；正确性修复：[M4 第二轮审查正确性修复](../../.agents/notes/implemented/bug-fix/2026-09-06-m4-correctness-repairs.md)

契约见已落地 note [`.agents/notes/implemented/architecture/2026-09-04-m1-core-document-contracts.md`](../../.agents/notes/implemented/architecture/2026-09-04-m1-core-document-contracts.md)。

语言包在 schema 落地后持有便利类型，不是独立真源：Python 绑定在 `packages/python/document-model`（Pydantic，生成），TypeScript 绑定在 `packages/typescript/document-model`（生成类型 + 运行时 schema 校验器）。
