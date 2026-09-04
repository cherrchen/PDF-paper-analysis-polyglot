# ID 策略

[中文](./id-policy.md) | [English](./id-policy.en.md)

权威定义：[`docs/architecture/document-architecture.md`](../architecture/document-architecture.md) §47；身份模型：[`docs/architecture/source-mapping.md`](../architecture/source-mapping.md)。

## 核心 ID 类型

```text
NodeID          — SemanticNode 跨 representation 稳定身份
RegionID        — Layout 区域
AnchorID        — Source / Render 锚点
EvidenceID      — Evidence 条目
ResourceID      — 图像、片段等资源
DocumentID      — 文档与 Bundle
ProvenanceID    — 来源记录
```

## 持久身份规则

- 使用 opaque persistent ID（建议 UUIDv7 / ULID）。
- 禁止 `paragraph_1`、`paragraph_2` 作为持久 identity。
- 跨 representation 的稳定身份是 `SemanticNodeID`，不是 page number、bbox、paragraph index。

## Reconciliation

保存 `source_fingerprint` 用于重新解析时的 ID reconciliation。ID 本身不负责语义匹配。

## Mapping 身份

SourceAnchor ↔ SemanticNode ↔ RenderAnchor 通过 Binding 建立 many-to-many 关系，不依赖页码对应。
