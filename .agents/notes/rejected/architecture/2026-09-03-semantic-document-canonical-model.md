# Agent Note: SemanticDocument 真源模型

Status: rejected — landed by later implemented notes; no longer current authority

[中文](./2026-09-03-semantic-document-canonical-model.md) | [English](./2026-09-03-semantic-document-canonical-model.en.md)

## 问题

Python、TypeScript 与 Rust 都会需要文档模型。各自独立的类型会分叉。

## 提案

把 `schemas/semantic-document/` 中的 JSON Schema 作为唯一契约真源。之后从该 schema 生成语言绑定。在产品字段明确后，一次性定义 Page、Block、TextSpan、BoundingBox、Figure、Table、Equation、Citation 与 SourceMapping。

## 考虑过的替代方案

- 按语言手写模型、靠约定同步，会漂移。
- 在没有 RPC 或二进制契约需求时，Protobuf 没有必要。

## 验收标准

- 一套 schema 拥有身份与必填字段
- 生成绑定有新鲜度检查
- 语言包不发明并行必填字段

## 风险

过早锁字段会在研究期间被迫做破坏性 schema 升级。
