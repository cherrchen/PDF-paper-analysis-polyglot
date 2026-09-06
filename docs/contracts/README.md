# 契约索引

[中文](./README.md) | [English](./README.en.md)

本目录索引跨语言契约与治理政策。完整模型定义见 [`docs/architecture/document-architecture.md`](../architecture/document-architecture.md)；机器可读 schema 见 `schemas/`。此处不重复完整 schema 正文。

## 文档模型契约

| 契约 | 权威位置 | 职责摘要 |
| --- | --- | --- |
| Document Architecture v0.1 | [`document-architecture.md`](../architecture/document-architecture.md) | 编译器式流水线、Bundle 结构、全层模型 |
| PhysicalDocument | 同上 §3 | PDF 客观内容：页、文本 span、图像、矢量、链接 |
| Evidence | 同上 §4 | 第三方 parser 输出；不得泄漏为 Layout/Semantic |
| LayoutDocument | 同上 §5–§8 | 视觉区域、栏、阅读顺序；不含论文语义 |
| SemanticDocument | 同上 §13–§17 | 逻辑结构；不含页面 geometry |
| Mapping | 同上 §18–§21 | Physical↔Layout↔Semantic↔Render 绑定 |
| RenderDocument | 同上 §25–§32 | 渲染中间表示与 RenderAnchor |

## 治理政策

| 政策 | 文档 |
| --- | --- |
| 层职责边界 | [`layer-responsibility.md`](layer-responsibility.md) |
| Parser Adapter | [`parser-adapter-contract.md`](parser-adapter-contract.md) |
| Schema 演进 | [`schema-evolution-policy.md`](schema-evolution-policy.md) |
| Provenance | [`provenance-policy.md`](provenance-policy.md) |
| ID 策略 | [`id-policy.md`](id-policy.md) |

## 架构决策

ADR 与已落地决策见 [`docs/decisions/`](../decisions/README.md) 与 `.agents/notes/`。

## Schema 真源

JSON Schema 位于 `schemas/`。M1 建立 common、physical-document、evidence、layout-document、semantic-document、mapping 的 `0.1.0` 开发基线；M2 Exit Gate 之后兼容性冻结已生效。M4 增加 `FOOTNOTE_REFERENCE` 而未升版本是记录例外，见 [schema 演进政策](schema-evolution-policy.md)。生成绑定（TS + Pydantic）与兼容性检查见 [`schemas/AGENTS.md`](../../schemas/AGENTS.md)、`just generate-check` 与 `just schema`。
