# Parser Adapter 契约

[中文](./parser-adapter-contract.md) | [English](./parser-adapter-contract.en.md)

权威定义：[`docs/architecture/document-architecture.md`](../architecture/document-architecture.md) §4、§34–§43。

## 核心规则

```text
Third-party parser output → Adapter → Evidence → Internal Recovery → Our Document Model
```

Parser 输出**永远不是** LayoutDocument 或 SemanticDocument。

## Adapter 职责

每个 Adapter 必须：

1. 将 provider-specific 输出映射为统一 `Evidence` 与子类型（`RegionCandidate`、`TableCandidate` 等）。
2. 记录 `ProvenanceRecord`（producer、version、operation、input_refs）。
3. 保留原始 confidence 与 geometry，供 Recovery 消费。
4. 不向上游泄漏 provider schema 类型。

当前实现：默认 capability registry 仍是 `mock` / `docling-sim` / `grobid-sim`。`mineru` / `docling` / `grobid` 把录制 dump（可选活服务）映射为 `EvidenceBundle`；第三方 schema 不得出 adapter。Docling 须转换 `coord_origin` 并消费 `table_cells`；MinerU 公式 ID 含页标识；GROBID 活路径 `POST /api/processFulltextDocument` 使用 multipart 字段 `input`。升级须走 §11 benchmark，禁止因为 adapter 存在就替换 production provider。

## Capability 归属

Parser 按 capability 注册，不按“全家桶”默认全跑。权威分配见 Document Architecture §35 Capability Registry。

## 冲突解决

禁止简单 majority vote。采用 Capability Authority、Confidence、Geometry Consistency、Cross-source Evidence、Internal Rules（§43）。

## 升级政策

依赖升级须走 upgrade branch → adapter 兼容 → benchmark → regression report → decision。见 [`docs/development/roadmap.md`](../development/roadmap.md) §11。
