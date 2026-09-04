# Agent Note: M2 Walking Skeleton 端到端管线落地

Status: implemented

[中文](./2026-09-04-m2-walking-skeleton.md) | [English](./2026-09-04-m2-walking-skeleton.en.md)

> 2026-09-05 Review 曾重新打开 M2 Exit Gate，修复后已再次通过。本文保留最初落地内容与理由；修正后的契约与验证结果见 [M2 Review 修复 Note](../bug-fix/2026-09-05-m2-review-repairs.md)。

## 问题

M1 冻结了五层 canonical schema，但全部功能代码仍是 stub：没有 PDF 摄入、没有恢复管线、没有渲染、没有查看器。M2（Walking Skeleton）要求建立第一条真正的端到端闭环——故意不追求解析质量，验证架构真实成立。

## 决策

七个 Phase 全部完成，管线与产物如下：

1. **PDFium 选型（Phase 2.1 前置）**：通过 `pypdfium2`（4.30，Apache-2.0/BSD 双许可绑定 + Google PDFium BSD 风格许可）接入 PDFium，新增为 `packages/python/pdf-pipeline` 依赖。依据 [Python / Rust 性能边界](../../proposed/architecture/2026-09-03-python-rust-performance-boundary.md)：无 benchmark 证据前不动 Rust，编排与提取留在 Python。
2. **Physical backend（2.1）**：`pdf_pipeline.physical.extract_physical_document` 从 PDF 字节提取 Page / TextSpan / ImageObject / Geometry 到 canonical page space（origin top-left, y down），输出校验过的 `PhysicalDocument`。行片段按垂直重叠 + 水平间距合并成 span。**确定性**：ID 由 `pdf_pipeline.ids.stable_uuid`（source fingerprint + 稳定计数）派生，同一 PDF 字节重复解析产出逐字节相同的文档（Roadmap 1.2 遗留到 M2.1 的要求）。
3. **Minimal layout（2.2）**：`pdf_pipeline.layout.recover_layout_document` 仅产出 TEXT / FIGURE region + HEADING_LIKE label（字号中位数比值启发式）、每页一个 band、朴素栏检测（完全位于半页内的 span 测量栏沟），ReadingFlowGraph 为真源、primaryFlow 线性派生。双栏检测在 BERT（ICLR 双栏 16/16 页）与 Attention（NeurIPS 单栏）上验证正确。
4. **Minimal semantic recovery（2.3）**：`pdf_pipeline.semantic.recover_semantic_document` 仅产出 HEADING / PARAGRAPH / FIGURE / FIGURE_CAPTION 节点（DOCUMENT 为根），caption 启发式为「figure 下方紧邻且横向重叠的短文本」，CAPTION_OF 关系连接二者。语义层零几何，`validate_layer_separation` 与 `validate_bundle_references` 全绿。
5. **Dummy translation（2.4）**：`paper_llm.translation` 提供 `DummyTranslationProvider`（`[TRANSLATED]` 前缀）与 `translate_document`。身份验证：node id、relations、树形状在翻译后保持不变，只有文本节点 content 改变。
6. **LaTeX renderer（2.5）**：`templates/latex/generic-academic.tex`（heading/paragraph/figure/caption）+ `pdf_pipeline.render_latex` 投影层。遵循 [LaTeX 渲染模型](../../proposed/architecture/2026-09-03-latex-render-model.md)：模板管呈现、投影管结构、TeX 永不进入 SemanticDocument、单一后端无 Renderer trait。
7. **RenderAnchor（2.6）**：投影为每个节点输出 `\renderanchor{<nodeId>}`（hyperref hypertarget）；编译后 `pdf_pipeline.render_anchor.recover_render_anchors` 用 PDFium named-destination API（UTF-16LE 名称解码）把 SemanticNode id 恢复成 target page + 坐标，写入 `MappingBundle` 的 RenderBinding/RenderAnchor。anchor id == SemanticNode id，三向映射 `SourceAnchor ↔ SemanticNode ↔ RenderAnchor` 建立。坐标 y 按页高翻转到 canonical space。
8. **Viewer（2.7）**：`apps/web` 引入 `pdfjs-dist`，双栏 Source/Target PDF 画布；`pdf_pipeline.pipeline.run_pipeline` 生成 `viewer/data/`（source.pdf、target.pdf、mapping.json、viewer-meta.json）供前端静态获取。Playwright e2e（`tests/e2e/viewer-navigation.spec.ts`）锁定映射数据覆盖与双画布加载。
9. **编排与回归**：`python -m pdf_pipeline run <input.pdf> <outdir>` 一次跑完全链，输出五份 canonical JSON + target PDF + viewer 数据，并跑 bundle 引用完整性。端到端确定性验证：重复运行五份 JSON 逐字节相同。`tests/golden/smoke/semantic.json` 为 smoke 夹具的 golden SemanticDocument（按 `docs/testing/golden.md` 流程建立）。
10. **Phase 2.1 真实论文验证**：`packages/python/pdf-pipeline/tests/test_physical_external.py`（`slow` marker）下载 3 篇 arXiv 公开论文（Attention Is All You Need / BERT / GPT-3，缓存于 `tests/fixtures/external/papers/`，gitignore 不入库），断言页数正确、标题/摘要文本完整、text span 坐标在页内。真实 PDF 中图片可以合法越界（渲染时被裁剪），physical 层如实记录不裁剪。

## 考虑过的替代方案

- PyMuPDF：AGPL 许可与仓库「Source-available 非商用」条款冲突风险高；PDFium 双 BSD 兼容。
- Rust `crates/pdf-core` 实现 backend：无热点测量，FFI 成本先行，违反性能边界 note。
- RenderAnchor 走 LaTeX 注释或坐标反推：身份模型 note 明确映射必须是一等数据持久化，且注释在重新排版后不稳定。
- 双栏检测用 x 中点直方图：被页码、页眉、跨界标题干扰；改为「完全半侧内 span + 栏沟宽度」后稳定。

## 后果

- M2 Exit Gate 达成：PDF → Physical → Layout → Semantic → Translation → LaTeX → Target PDF → 双向导航全链成立，五份产物全部通过 canonical 校验与跨层检查，且端到端可复现（逐字节确定）。
- 新增依赖：Python `pypdfium2`（pdf-pipeline），npm `pdfjs-dist`（apps/web）。`apps/web/public/data/`（管线生成的 viewer 数据）与 `tests/fixtures/external/` 已加入 `.gitignore`。
- 新 fixture：`figure-caption`（源 `.tex` + 占位 PNG + metadata），已入 Tier-1 表。
- 已知限制（有意保留给 M3+）：caption/heading 启发式粗糙、每页单 band、栏检测为朴素版、FigureContent 未携带真实资源 id、viewer 跳转目前验证映射数据与画布加载（区域级点击跳转在 UI 上叠加渲染坐标即可启用，映射数据已就位）。
- 解析质量提升从 M3（Layout Recovery Engine）开始；本骨架的层边界与 ID 稳定性是其后所有工作的地基。
