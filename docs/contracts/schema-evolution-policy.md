# Schema 演进政策

[中文](./schema-evolution-policy.md) | [English](./schema-evolution-policy.en.md)

权威定义：[`docs/architecture/document-architecture.md`](../architecture/document-architecture.md) §46；实现约束：[`schemas/AGENTS.md`](../../schemas/AGENTS.md)。

## 版本语义

| 级别 | 含义 | 要求 |
| --- | --- | --- |
| PATCH | 添加 optional 字段 / bug fix | 向后兼容；`just schema` 通过 |
| MINOR | 添加向后兼容能力 | 同上；更新 fixtures |
| MAJOR | 破坏性结构变更 | migration + fixture + compatibility test + ADR |

## 核心 schema 范围

```text
PhysicalDocument
LayoutDocument
SemanticDocument
RenderDocument
Evidence
Mapping
```

必须 versioned、serializable、language-neutral。Canonical 格式：JSON Schema。

## 生成与新鲜度

```text
Canonical schema → deterministic generator → Python / TypeScript / Rust bindings
```

生成代码禁止手改。CI 通过 `just generate-check` 校验新鲜度。

## 变更流程

1. Schema first, implementation second。
2. 先更新 `schemas/` 与 `schemas/fixtures/`。
3. 运行 `just generate` 与 `just schema`。
4. MAJOR 变更写 ADR 并提供 migration。

## 路线图交叉引用

开发顺序与 Exit Gate：[`docs/development/roadmap.md`](../development/roadmap.md) Milestone 1 Phase 1.7、§10。
