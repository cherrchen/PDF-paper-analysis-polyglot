# Agent Note: 产品需求文档 v0.2

Status: implemented

[中文](./2026-09-06-product-requirements-v02.md) | [English](./2026-09-06-product-requirements-v02.en.md)

## 问题

`docs/product/requirements.md` v0.1 在第 36 节保留 8 项开放产品问题（扫描 PDF、目标双栏、双语 PDF、Figure 内文字、References 翻译、SemanticDocument 编辑、Translation Provider 定位、运行形态）。在 M5 启动前，Initial Product 边界必须闭合，否则架构与 Milestone 会继续以未决需求为借口漂移。

## 决策

1. 以 PRD **v0.2** 完整覆盖 v0.1，作为当前用户需求的唯一真源（`docs/product/requirements.md` + `requirements.en.md`）。
2. 原 §36 八项开放问题全部闭合；决策摘要见 PRD §43 与 §50。
3. 下游 Architecture、Schema、Roadmap、Milestone 以 v0.2 为上游约束；技术冲突时优先调整技术方案，不静默改写产品需求。
4. 本次变更记为显式 Requirements Change；延续 [产品需求文档 v0.1 建立](./2026-09-06-product-requirements.md) 的流程约定。

### v0.2 已确认的 Initial Product 边界（摘要）

| 主题 | Initial Product |
| --- | --- |
| 输入 | Born-digital PDF only |
| Target 布局 | 默认适合译文阅读的单栏 |
| Target 内容 | 纯译文 |
| Viewer | Source / Target 双文档联合阅读 |
| Figure | Caption 可译；图内文字不译；Asset 保持原样 |
| References | 不翻译 |
| SemanticDocument | 用户不可编辑；架构预留人工修正 |
| Translation | Provider Agnostic；允许外部服务 |
| 运行时 | Local-first |
| Server + Web | Post-Initial |

## 与现有设计/实现的冲突审查

以下按「当前必须修正」与「文档/计划对齐或延期处理」分类。**未要求大规模重构。**

### A. 当前必须在 M5 前修正（实现与 v0.2 直接冲突）

审查当时把「排除 `BIBLIOGRAPHY_ENTRY`」写成 M5 任务，与「必须在 M5 前修正」冲突。该项已在 M5 前落地，见 [参考文献不翻译（FR-CITE-004）](../architecture/2026-09-06-bibliography-not-translated.md)。

| 冲突 | 证据 | 受影响 | 说明 |
| --- | --- | --- | --- |
| References 被纳入可翻译节点 | `packages/python/llm/src/paper_llm/translation.py` 中 `TEXT_NODE_KINDS` 曾含 `BIBLIOGRAPHY_ENTRY`；`translate_document` 会对参考文献条目加 `[TRANSLATED]` 前缀 | 翻译层（M5 前） | **已解决。** 违反 PRD FR-CITE-004 / §43「References 不翻译」。现已从 `TEXT_NODE_KINDS` 排除 `BIBLIOGRAPHY_ENTRY` 并补回归测试；不是 M5 范围。 |

### B. 文档与计划对齐（现在改文档/计划，实现可随 Milestone 跟进）

| 冲突 | 证据 | 受影响 | 说明 |
| --- | --- | --- | --- |
| Roadmap M5 提及 `SourceDerivedProfile` | `docs/development/roadmap.md` 建议下一步 | M5、R2 | v0.2 将「继承 Source 布局特征」定为 Post-Initial（PRD §23、R2）。M5 默认 `readable-single-column`；`SourceDerivedProfile` 仅作架构预留，不作为 Initial Product 验收。 |
| Document Architecture 未区分 OCR 阶段 | `docs/architecture/document-architecture.md` §37 将「扫描 PDF → OCR」与 born-digital 路径并列，未标 Post-Initial | Architecture v0.1 | 架构可保留扩展路径，但应注明 Initial Product 不支持扫描输入（PRD NG1、FR-PDF-002）。 |
| Roadmap 语料与 M7 将扫描 PDF 列为同等首批能力 | `docs/development/roadmap.md` Phase 0.3、M7 Phase 7.3 | M0/M7 | Tier 4 扫描夹具可保留为 **Post-Initial 研究占位**（`tests/fixtures/metadata/scanned-external.yaml`），不应解读为 Initial Product 输入契约。 |
| Born-digital 输入检测未实现 | 无 `FR-PDF-002` 对应产品级拒绝路径 | M5 前产品集成 | 缺口而非反向实现；Initial Product 需明确拒绝扫描/无文本层 PDF。 |

### C. 已对齐或仅延期（无需现在重构）

| 主题 | 状态 |
| --- | --- |
| Target 单栏 LaTeX | `templates/latex/generic-academic.tex` 使用 `article` 单栏；符合 FR-LAYOUT-004 |
| 纯译文、无双语 PDF | 当前管线仅生成译文层；符合 FR-OUTPUT-001 |
| Figure Caption 可译 | `TEXT_NODE_KINDS` 含 `FIGURE_CAPTION` |
| Figure Asset / 图内文字 | 资源链仍在 M5；不翻译图内文字为产品决策，非冲突 |
| Translation Provider 抽象 | `TranslationProvider` Protocol + `DummyTranslationProvider`；符合 `FR-PROVIDER-*` |
| Source↔Target Viewer | M2 Walking Skeleton 已验收双文档语义导航；符合 `FR-SYNC-*` / `FR-VIEW-*` |
| SemanticDocument 不可编辑 | 无用户编辑 UI；Schema 保留 stable ID / provenance |
| Local-first、Domain 与 UI 分离 | 核心模型在 `schemas/`、`packages/python/`；`apps/` 为薄壳，未把 Domain 绑死 Desktop |
| Bilingual PDF、Figure 内译、Semantic 编辑、Server 化 | PRD §44 Post-Initial；刻意延期 |

## 考虑过的替代方案

- 保留 v0.1 并把 v0.2 当附录：会造成双真源，违反用户要求。
- 仅在 Roadmap 口头闭合八项问题、不升 PRD 版本：无法作为 Requirements Change 审计。
- 立即大规模改代码以消除所有缺口：超出本次范围；仅标记 M5 前必须项。

## 后果

- 所有新 Plan、Implementation Decision、Milestone 验收以 PRD v0.2 为上游。
- M5 启动检查须包含：默认单栏 RenderProfile、born-digital 输入拒绝（或等效 UX）。References 不翻译已在 M5 前落地，见 [参考文献不翻译（FR-CITE-004）](../architecture/2026-09-06-bibliography-not-translated.md)。
- Architecture v0.1 与 Roadmap v0.1 仍为技术契约真源，但与产品冲突时以 PRD v0.2 为准并记录对齐项。
- [产品需求文档 v0.1 建立](./2026-09-06-product-requirements.md) 中「§36 待闭合」的表述由本 note 取代。
