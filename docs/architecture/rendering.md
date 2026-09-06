# 渲染

[中文](./rendering.md) | [English](./rendering.en.md)

渲染架构见 [`document-architecture.md`](document-architecture.md) 第 25–32 节。

当前实现路径（M2–M4）：

```text
SemanticDocument
+
TranslationLayer
      ↓
compose_render_document(semantic, translation)
      ↓
RenderDocument
      ↓
LaTeX Backend
      ↓
LuaLaTeX
      ↓
PDF
```

冻结架构第 26–32 节中的 RenderProfile / RenderPolicy 是 M5 的目标接口。现行 `compose_render_document` 只接受 SemanticDocument 与 TranslationLayer，内部写死 `generic-academic` profile 与 `floatFigures=True`。TABLE / EQUATION / BIBLIOGRAPHY_ENTRY 投影为段落，TABLE_CAPTION 独立输出，避免静默丢内容；真实表格与公式排版属于 M5。

- 模板：`templates/latex/`
- 翻译层契约：[`schemas/translation-layer/schema.json`](../../schemas/translation-layer/schema.json)
- 渲染文档契约：[`schemas/render-document/schema.json`](../../schemas/render-document/schema.json)
- 引擎策略：`tex/README.md` 与 [`docs/development/latex.md`](../development/latex.md)
- LaTeX 后端决策：[`.agents/notes/implemented/architecture/2026-09-03-latex-as-initial-rendering-backend.md`](../../.agents/notes/implemented/architecture/2026-09-03-latex-as-initial-rendering-backend.md)
- 文档架构 v0.1：[`.agents/notes/implemented/architecture/2026-09-03-document-architecture.md`](../../.agents/notes/implemented/architecture/2026-09-03-document-architecture.md)

RenderComposer 把语义节点与可选译文合成为 RenderDocument；图像与 FIGURE 的 `CAPTION_OF` 标题在此阶段绑定为同一个渲染块，TABLE_CAPTION 保持独立块。LaTeX Backend 只消费 RenderDocument，不直接从 SemanticDocument 生成出版社特定 LaTeX。没有多渲染器接口；Typst 为未来扩展。
