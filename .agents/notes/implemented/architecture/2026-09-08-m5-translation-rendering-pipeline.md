# Agent Note: M5 Translation & Rendering Pipeline 落地

Status: implemented

[中文](./2026-09-08-m5-translation-rendering-pipeline.md) | [English](./2026-09-08-m5-translation-rendering-pipeline.en.md)

## 问题

M4 完成后翻译层仍为 dummy 前缀，渲染层仅有段落/标题/图占位，无法满足 M5 Exit Gate：真实翻译、完整学术内容排版、自然单栏重排、全节点多 fragment RenderAnchor。

## 决策

1. **Schema 0.2.0**（additive）：`translation-layer` 增术语表/providerModel/cacheKey；`render-document` 增 Profile/Policy 参数与 TABLE/EQUATION/BIBLIOGRAPHY block；新增 `ResourceDocument`。
2. **翻译栈**（`paper_llm`）：`TranslationRequest/Result` 结构化协议；`build_translation_contexts`；术语发现与 `PAPER_TERMINOLOGY_FILE` 手工覆盖；JSONL 翻译缓存；`OpenAICompatProvider`（httpx，环境变量配置）；默认 CI 走 Dummy/mock。
3. **渲染栈**（`pdf_pipeline`）：`compose_render_document(..., profile, policy, resources)`；`resource_store` 提取嵌入图；`math_latex` unicode 兜底；LaTeX 真表格/公式/书目/`\includegraphics`；双 hypertarget RenderAnchor。
4. **推迟**：1 Layout→N Semantic（建议 M7）、MathML、`dense-two-column` profile。

## 考虑过的替代方案

- 厂商 SDK：违背 Provider Agnostic，否决。
- 扫描 PDF 静默恢复：FR-PDF-002 已在 5.0 入口拒绝。
- `physical-document` 内嵌 ResourceStore：触碰冻结 schema，改用独立 `ResourceDocument`。

## 后果

- `run_pipeline` 产出 `resources.json` 与 `out/resources/` 图像文件。
- 真实 LLM 需设置 `PAPER_LLM_ENDPOINT` 等环境变量；golden/E2E 仍用 Dummy 保证确定性。
- 公式 unicode→LaTeX 有限转换，失败回退 `\text{...}` 不丢内容。
- 审查修复见 [M5 Review 修复](../bug-fix/2026-09-08-m5-review-repairs.md)：占位符保护、中文模板、源绑定图资源、跨页 fragment geometry。
- 保真与配置兑现见 [M5 内容保真修复](../bug-fix/2026-09-11-m5-fidelity-repairs.md)：公式兜底、多图投影、客户端所有权、缓存指纹与 RenderPolicy。
- 原 proposed 计划 note（`2026-09-07-m5-...`）保留为历史规划参考。

## 验收

- `just test-unit`、`just schema`、`just generate-check` 通过。
- Tier-1 smoke fixture 全链编译通过；书目不翻译；表单元格进 TranslationLayer。
- 文档：`docs/architecture/rendering.md` 更新为 M5 当前态。
