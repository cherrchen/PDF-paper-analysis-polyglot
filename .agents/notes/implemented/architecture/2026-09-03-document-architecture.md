# Agent Note: Document Architecture v0.1

Status: implemented

[中文](./2026-09-03-document-architecture.md) | [English](./2026-09-03-document-architecture.en.md)

## 问题

parser、renderer、viewer、translation 需要共享一套冻结的文档架构契约。此前相关设计分散在多个 proposed Agent Note 与占位架构页中，缺少单一权威基准。

## 决策

冻结 **Document Architecture v0.1** 作为跨层契约基准。权威文档：

- [`docs/architecture/document-architecture.md`](../../../../docs/architecture/document-architecture.md)

核心决策摘要：

- 四层独立模型：`PhysicalDocument`、`LayoutDocument`、`SemanticDocument`、`RenderDocument`
- 聚合根 `DocumentBundle`，含 mappings、derived layers、renders、provenance、issues
- 第三方 parser 只产出 Evidence，不直接定义 Layout / Semantic 模型
- `RenderComposer`（原 LayoutPlanner）从 Semantic + Translation + Profile + Policy 生成 Render IR
- LaTeX Backend 只消费 Render IR
- Capability Registry 明确 PDFium / MinerU / Docling / GROBID / internal 职责边界
- Schema first：JSON Schema 为跨语言契约真源

本决策部分取代以下 proposed notes（保留其历史推理，不再作为当前权威）：

- [`.agents/notes/proposed/architecture/2026-09-03-semantic-document-canonical-model.md`](../../proposed/architecture/2026-09-03-semantic-document-canonical-model.md)
- [`.agents/notes/proposed/architecture/2026-09-03-source-mapping-identity-model.md`](../../proposed/architecture/2026-09-03-source-mapping-identity-model.md)
- [`.agents/notes/proposed/architecture/2026-09-03-layout-reconstruction-pipeline.md`](../../proposed/architecture/2026-09-03-layout-reconstruction-pipeline.md)
- [`.agents/notes/proposed/architecture/2026-09-03-latex-render-model.md`](../../proposed/architecture/2026-09-03-latex-render-model.md)
- [`.agents/notes/proposed/architecture/2026-09-03-python-rust-performance-boundary.md`](../../proposed/architecture/2026-09-03-python-rust-performance-boundary.md)

与已落地 note [LaTeX 作为初始渲染后端](./2026-09-03-latex-as-initial-rendering-backend.md) 兼容：v0.1 将渲染路径细化为 RenderDocument → LaTeX，不改变 LaTeX 作为唯一一等后端。

## 考虑过的替代方案

- 继续以 proposed Agent Note 分散记录：不利于 parser / schema 并行开发。
- 直接跳过架构冻结、先写 parser adapter：会固化错误边界（尤其 Evidence vs Document）。
- 以单一 parser 输出作为 SemanticDocument 真源：违背 evidence-provider 原则。

## 后果

- 架构子页（overview、pipeline、pdf-ingestion、source-mapping、semantic-document、rendering）链到 `document-architecture.md`，不再标记为「有意未决」。
- 下一步工程化：在 `schemas/` 冻结五套核心 schema（Physical、Layout、Semantic、Mapping、Evidence），再实现 package API 与 parser adapter。
- 引入新 parser、渲染后端或改变层边界，需要新 Agent Note 并更新 v0.1 文档或发布 v0.2。
