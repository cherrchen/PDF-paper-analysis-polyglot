# Agent Note: 参考文献不翻译（FR-CITE-004）

Status: implemented

[中文](./2026-09-06-bibliography-not-translated.md) | [English](./2026-09-06-bibliography-not-translated.en.md)

## 问题

PRD v0.2 的 FR-CITE-004 规定 Initial Product 中 **References 不翻译**。M4 为防止 Target PDF 静默丢书目，把 `BIBLIOGRAPHY_ENTRY` 扩进 `paper_llm.TEXT_NODE_KINDS`，Walking Skeleton 因此给参考文献加 `[TRANSLATED]` 前缀。

[产品需求文档 v0.2](../process/2026-09-06-product-requirements-v02.md) 把此事标成「必须在 M5 前修正」，同时又写「M5 应排除 `BIBLIOGRAPHY_ENTRY`」。后者把修法推迟到 M5，与前者冲突：当前管线已经在翻译参考文献。

## 决策

1. **现在、在 M5 之前**从 `TEXT_NODE_KINDS` 排除 `BIBLIOGRAPHY_ENTRY`。这不是 M5 任务；M5 真实 provider 不得把参考文献重新纳入可译集合。
2. RenderComposer 继续把 `BIBLIOGRAPHY_ENTRY` 投影为段落。无 TranslationEntry 时回退到 SemanticDocument 原文，Target PDF 仍保留书目。
3. 回归测试锁定：schema 夹具与 `bibliography` 恢复夹具的条目不得进入 TranslationLayer；RenderDocument 中的条目文本等于原文且不含 `[TRANSLATED]`。
4. 本 note 部分取代 [M4 Semantic Recovery Engine](./2026-09-06-m4-semantic-recovery-engine.md) 决策 10 中「BIBLIOGRAPHY_ENTRY 直接可译」条款；渲染兜底（不丢内容）仍然有效。

## 考虑过的替代方案

- 等到 M5 再改：当前 dummy 路径已经违反 FR-CITE-004，M5 前的 Viewer / golden / 端到端产物都会带错误前缀。
- 仍写入 TranslationLayer、渲染时再换回原文：TranslationLayer 会成为假译文，Viewer 与分析层会把它当成已译内容。
- 只跳过 `BIBLIOGRAPHY` 容器：容器本身无正文；可译 kind 是 `BIBLIOGRAPHY_ENTRY`。

## 后果

- Dummy 翻译与后续真实 provider 都跳过参考文献条目；章节标题「References」仍作为 `HEADING` 可译。
- [产品需求文档 v0.2](../process/2026-09-06-product-requirements-v02.md) 冲突审查 A 项关闭；M5 启动检查不再把「排除参考文献翻译」列为待办。
