# Provenance 政策

[中文](./provenance-policy.md) | [English](./provenance-policy.en.md)

权威定义：[`docs/architecture/document-architecture.md`](../architecture/document-architecture.md) §22–§23。

## 一等公民

每个推断、提取、生成步骤必须可追踪。`ProvenanceRecord` 至少包含：

```text
id
producer / producer_version
operation
input_refs
parameters_hash (optional)
```

## Origin 语义

任何结果必须标注来源类别：

```text
SOURCE
EXTRACTED
INFERRED
GENERATED
USER
```

LLM 生成内容 ≠ 论文原文。AnalysisLayer 不得污染 Source SemanticDocument。

## 附着规则

以下对象应携带 `provenance_ids`（或等价引用）：

- Evidence 与 LayoutRegion
- SemanticNode 与 SemanticRelation
- TranslationEntry
- SourceAnchor

## Recovery 可观测性

Recovery Engine 输出 confidence、provenance、reason、issues。禁止“黑盒”推断而无来源链。
