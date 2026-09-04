# Agent Note: M1 核心文档契约落地

Status: implemented

[中文](./2026-09-04-m1-core-document-contracts.md) | [English](./2026-09-04-m1-core-document-contracts.en.md)

## 问题

Document Architecture v0.1 已冻结，但核心契约只存在于文档中：`schemas/` 只有一个 `0.0.0-unresolved` 的 SemanticDocument placeholder，Python / TypeScript 包没有真实模型，生成器没有注册任何生成器。M1（Core Document Contracts）要求冻结 Physical / Evidence / Layout / Semantic / Mapping 五层 schema，并建立跨语言一致性与层职责验证。

## 决策

M1 全部七个 Phase 完成，进入当前态：

1. **六套 canonical JSON Schema**（`schemas/<name>/schema.json`，版本 `0.1.0`）：
   - `common` — ID 类型（ULID/UUID pattern，含 LayoutGroupID）、Provenance、Origin、Resource、Issue、Geometry（Rect/Quad/Polygon）、Matrix、LayoutLabel
   - `physical-document` — 页、TextSpan、ImageObject、VectorObject、LinkObject、Canonical Page Space
   - `evidence` — RegionCandidate、TableCandidate、FormulaCandidate、StructureCandidate、MetadataCandidate；provider 字段禁止 extra keys，原生标签保留在 `providerLabel`
   - `layout-document` — LayoutRegion、PageBand、Column、LayoutGroup、ReadingFlowGraph（graph 为 source of truth，`primaryFlow` 为派生）、ReadingOrderReason
   - `semantic-document` — SemanticNode（树）+ SemanticRelation（图）、RichText/InlineMark（`TextNodeContent` 为 RichText 别名）、NodeContent（text/figure/table/equation）；替换原 placeholder
   - `mapping` — PhysicalLayoutBinding、SourceAnchor（v0.1 仅 LayoutRegionRef fragment）、SourceSemanticBinding、RenderAnchor/RenderBinding
2. **确定性生成器** `scripts/generate.py`（`just generate` / `just generate-check`）：从 schema 生成 TS 类型（`packages/typescript/document-model/src/generated/schema.ts`）与 Pydantic 模型（`packages/python/document-model/src/document_model/generated/schema_models.py`）。可选字段按 JSON Schema 可省略、默认不可 null；`pattern` / `maxItems` / 数值约束进入生成模型。生成后对 Pydantic 文件跑 Ruff format，使新鲜度检查与 `just fmt` 一致。所有 `$defs` 名称跨 schema 全局唯一，因此两侧均为扁平命名空间。生成物禁止手改，CI 做新鲜度检查。
3. **TS 运行时校验器** `packages/typescript/document-model/src/validate.ts`：直接读取 canonical JSON Schema 文件做运行时验证（覆盖 schema 所用的 JSON Schema 子集与跨文件 `$ref`），保证生成类型不会与契约漂移。
4. **Python 辅助层**：`document_model.ids`（ULID 式 opaque ID）、`document_model.serialize`（`dump_document`/`load_document`）、`document_model.validators`（层职责检查 + bundle 引用完整性）。
5. **fixtures**（`schemas/fixtures/`，由 `scripts/build_fixtures.py` 确定性生成）：双栏 + 跨栏 Figure + Footnote 的 Physical/Layout 文档、含全部必需 NodeKind 的 Semantic 文档、mock provider Evidence（含 StructureCandidate）、覆盖 N→1 / 1→N / N→N 以及跨页 N→1 的 Mapping。Fixture ID 把序号放在尾部以避免碰撞。
6. **跨语言 roundtrip 集成测试** `tests/integration/test_cross_language_roundtrip.py`：Python serialize → JSON → TS validate/re-serialize → Python parse，语义一致；TS 侧拒绝几何信息进入 semantic 层。审查后的等价性与引用完整性补丁见 [M1 契约审查修复](./2026-09-04-m1-review-repairs.md)。

## 考虑过的替代方案

- Pydantic 模型手写、TS 类型手写：与 canonical schema 必然漂移，违背 Schema first 原则。
- 引入 datamodel-code-generator / json-schema-to-typescript 等第三方生成器：引入重依赖且输出不可控；本项目 schema 规模小，自持确定性生成器更可维护。
- Python 侧 `oneOf` 用 Pydantic discriminated union：当前 union 变体自带 Literal 判别字段，普通 union alias 已可在文档级完成与 JSON Schema 一致的校验。
- RenderDocument schema：架构文档 §25–§32 有设计，但 M1 范围只要求五层；Render schema 推迟到 M2 的 RenderAnchor 工作时冻结。

## 后果

- M1 Exit Gate 五项条件全部满足：核心 schema versioned（`0.1.0`）、roundtrip 稳定（含非法 payload 拒绝）、第三方 parser schema 不泄漏（EvidenceBundle `additionalProperties: false` 由测试锁定）、层职责测试完成、mapping many-to-many 验证完成（N→1 / 1→N / N→N 与跨页 fixture + 测试）。Phase 1.2 在 M1 验证 JSON 反序列化稳定性；同一 PDF 字节重复解析属于 M2.1。
- `just schema` 校验六套 schema 与全部 fixtures；`just generate-check` 锁定生成物新鲜度；`just test-integration` 需要本机有 `node`（M0 起已是必装工具）。
- SemanticNode `attributes` 是 schema 中唯一 `additionalProperties: true` 的位置（开放 attribute bag）；层边界由 `document_model.validators.validate_layer_separation` 在文档级强制（bbox/page/column 等进入 semantic 层会被判违规）。
- 下一阶段 M2 Walking Skeleton 可直接依赖这五层 Pydantic/TS 模型实现最小 PDF 后端、layout/semantic recovery 与渲染。
