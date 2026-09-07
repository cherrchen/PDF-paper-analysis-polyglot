# Agent Note: M5 Translation & Rendering Pipeline 开发计划

Status: proposed

[中文](./2026-09-07-m5-translation-rendering-pipeline.md) | [English](./2026-09-07-m5-translation-rendering-pipeline.en.md)

## 问题

M4 语义恢复基线已落地（两轮正确性修复后），下一阶段为 roadmap M5：从占位翻译升级为真实可靠的学术论文翻译与自然重排。当前缺口：

- 翻译层仍是 M2 dummy（`[TRANSLATED]` 前缀），无真实 provider、无上下文、无术语、无缓存。
- RenderDocument 只有 HEADING/PARAGRAPH/FIGURE 三种 block；RenderProfile/RenderPolicy 在 `compose_render_document` 内写死。
- TABLE/EQUATION/BIBLIOGRAPHY_ENTRY 投影为纯文本段落兜底；图渲染为空白 `\fbox` 占位；RenderAnchor 为单 fragment 命中点。
- PRD v0.2 启动检查指出的 FR-PDF-002（born-digital 拒绝路径）缺口。

M5 Exit Gate：真实翻译 + 完整 academic content + 自然 LaTeX reflow + 所有主要节点 RenderAnchor。

## 提案

按 roadmap Phase 5.1–5.8 推进，范围决策（已与产品确认）：

1. **Provider**：首个真实接入为 OpenAI 兼容 Chat Completions HTTP Adapter（Endpoint/API Key/Model 可配置，兼容 GLM/DeepSeek/Ollama/vLLM）。
2. **Profile**：仅实现默认 `readable-single-column` 单栏 Profile + RenderPolicy 体系；`dense-two-column`、`source-derived` 不做（后者属 Post-Initial R2，PRD §23）。
3. **M4 延期项**：纳入「图资源链」「公式 LaTeX 排版」；1 Layout→N Semantic（建议 M7）与 MathML 明确推迟。

### Phase 5.0 启动检查（已完成，commit 0ddb3df）

- `pdf_pipeline.physical.probe_input_capability`：任何页有有效文本层即可用；无文本层在 `run_pipeline` 入口抛出带用户可读原因的 `ValueError`（FR-PDF-002）。
- BIBLIOGRAPHY_ENTRY 不翻译的回归防护已有测试（`test_translation.py::test_bibliography_entries_are_not_translated` 等）。

### Phase 5.1+5.6 Schema 0.2.0 additive 升级（进行中，未提交）

工作区已含未提交变更：

- `translation-layer` 0.1.0 → 0.2.0：TranslationEntry 增 `providerModel`/`cacheKey`；顶层增 `providerModel`/`terminologyRevision`/`terminology[]`；新增 `Term`（term/preferredTranslation/source/confidence/scope，source ∈ MANUAL/DERIVED/PROVIDER，scope ∈ DOCUMENT/SECTION）。
- `render-document` 0.1.0 → 0.2.0：RenderProfile 增 `columns`/`paperSize`/`fontSizePt`/`lineSpacingFactor`；RenderPolicy 增 `floatTables`/`wideFigureHandling`/`tableOverflowHandling`/`longEquationHandling`/`captionPosition`（Wide 变体由 Policy 推导，不单独建 IR 类型）；新增 `RenderTableBlock`（table + caption + columnAlignments）、`RenderEquationBlock`（equation）、`RenderBibliographyBlock`（entries：semanticNodeId + RichText）；RenderFigureBlock 增 `resourceIds[]`。
- 新增 `schemas/resources/`（ResourceDocument 0.1.0 起步，包装 common 的 ResourceStore，携带 sourceFingerprint）；已注册进 `scripts/generate.py`、`scripts/verify_schemas.py`、`document_model/serialize.py` 的 `_ROOT_MODELS`。
- fixtures 已更新至 0.2.0（translation-layer/render-document），新增 `schemas/fixtures/resources/embedded-image.valid.json`。
- 绑定已重生成（`scripts/generate.py`）；**尚未运行** `just schema` 全量校验与下游代码适配（`paper_llm/translation.py`、`render_composer.py` 仍写 `schemaVersion="0.1.0"`，会校验失败）。

### 后续 Phase（未开始）

- **5.1 结构化翻译协议**：Provider Protocol 从 `translate(str) -> str` 升级为 `TranslationRequest`（节点文本 + marks + context + terminology + locale）→ `TranslationResult`（译文 + 占位符回执 + confidence）；占位符保护覆盖 CITATION/INLINE_EQUATION/FOOTNOTE_REFERENCE 及 Figure/Table/Equation 引用全部 mark 类型；Table Cell 翻译对齐 FR-TRANS-001（树形状/关系不变）。
- **5.2 翻译上下文**：document metadata、section 标题链、neighbor paragraphs（截断窗口）、术语表注入；prompt 组装留在 provider adapter（FR-PROVIDER-004）。
- **5.3 术语系统**：候选抽取 → LLM 确认首选译名（Source=DERIVED）→ 手工覆盖文件（Source=MANUAL）；术语更新递增 `terminologyRevision`。
- **5.4 翻译缓存**：cache key = hash(node content, target locale, model, config, terminology revision)；本地持久化；单段重译不需重解析 PDF（FR-TRANS-004/005）。
- **5.5 OpenAI 兼容 Adapter**：httpx 客户端 + 重试/超时/错误分类；占位符丢失降级丢 marks 记 Issue；CI 走 mock HTTP server，真实 key smoke 标 slow。
- **5.6 RenderProfile/Policy 参数化**：`compose_render_document(semantic, translation, profile, policy)`，删除写死值；默认 profile 定名 `readable-single-column`；模板 `generic-academic.tex` 参数化。
- **5.7 LaTeX 后端**：真表格（`TableContent.cells` → tabular，overflow 按 Policy 降级不丢内容）、公式（unicode/rawText → LaTeX math 有限确定性转换，失败回退 `\text{}`；公式不进翻译 FR-EQ-004/005）、图资源链（pypdfium2 提取嵌入图像 → ResourceStore → `FigureResource.embeddedImageIds` 填充 → `\includegraphics`）、书目（BIBLIOGRAPHY block → thebibliography 或条目段落）、RenderAnchor 双 hypertarget（`<nodeId>` 起始 + `<nodeId>:end` 结束）恢复为多 fragment。
- **5.8 验收**：golden 走人工审查 bless（禁为过测试改 golden）；单测断言文本跨度与跨层绑定而非节点计数；E2E 双 Viewer 导航；Agent Notes（schema 0.2.0 升级、Provider Adapter、ResourceStore、RenderProfile/Policy、M5 总落地）+ 当前态文档 + roadmap 状态 + CHANGELOG。

## 考虑过的替代方案

- 仅升级抽象接口不接真实 provider：Exit Gate「真实翻译」无法达成，已否决。
- 指定厂商 SDK：违背 Provider Agnostic（FR-PROVIDER-001~004），OpenAI 兼容 HTTP 覆盖面更广。
- 实现 dense-two-column：增加 M5 工作量与测试面，PRD Initial Product 只验收默认单栏。
- 把 resourceStore 字段加进 frozen 的 physical-document（需其也升 0.2.0）：改用独立 ResourceDocument，零冻结 schema 触碰。
- 1 Layout→N Semantic 与 MathML 纳入 M5：偏离翻译+渲染主题，推迟（1→N 建议 M7）。

## 验收标准

- Exit Gate 四项全绿：真实翻译（mock 驱动全链 + 手动真实 key smoke）、完整 academic content（图/表/公式/书目/脚注真实排版）、自然 LaTeX reflow（单栏、允许页数变化）、所有主要节点 RenderAnchor 含跨页多 fragment。
- `just schema`、`just generate-check`、`just ci` 通过；additive 升级有 Agent Note 记录。
- FR-PDF-002：扫描/无文本层 PDF 在入口被明确拒绝。
- BIBLIOGRAPHY_ENTRY 不被真实 provider 重新纳入可译集合（回归测试通过）。

## 风险

- 公式 unicode→LaTeX 转换兜底覆盖率不足 → 已设计 `\text{}` 原文回退，不丢内容。
- 图资源提取跨平台确定性 → 资源字节指纹参照既有 PDF 指纹重映射经验处理。
- schema 0.2.0 升级半途（绑定已重生成、代码未适配）→ 工作区不可直接 `just check`，需先完成下游 `schemaVersion` 适配再验证。
- 真实 LLM 输出非确定性 → golden/E2E 全部走 Dummy/mock，真实 provider 仅 slow 手动 smoke。

## 当前进度与交接（截至 2026-09-07）

- 已提交：`0ddb3df feat(m5): reject scanned PDFs at pipeline entry (FR-PDF-002)`（physical.py probe + pipeline 入口 + 5 个单测，全绿）。
- 未提交（工作区）：上述 schema 0.2.0 全部变更 + 重生成绑定。**下一步第一件事**：适配 `paper_llm/translation.py` 与 `render_composer.py` 的 `schemaVersion="0.2.0"`，跑 `just schema` + `just generate-check` + `just test-unit`，通过后以 `feat(schema): bump translation-layer and render-document to 0.2.0` 提交。
- 详细分阶段计划、验收清单与测试纪律见上文提案节；实施顺序 5.1 → 5.2 → 5.3 → 5.4 → 5.5 → 5.6 → 5.7 → 5.8（5.1 与 5.6 的 schema 变更已合并为本次 0.2.0 升级）。
