# 渲染

[中文](./rendering.md) | [English](./rendering.en.md)

渲染架构见 [`document-architecture.md`](document-architecture.md) 第 25–32 节。

当前实现路径（M5）：

```text
SemanticDocument
+
TranslationLayer
      ↓
compose_render_document(semantic, translation, profile, policy, resources)
      ↓
RenderDocument  (HEADING / PARAGRAPH / FIGURE / TABLE / EQUATION / BIBLIOGRAPHY)
      ↓
LaTeX Backend  (generic-academic.tex + profile 参数)
      ↓
LuaLaTeX
      ↓
PDF
```

默认 Profile 为 `readable-single-column`（A4、11pt、1.25 行距、单栏）。模板通过 `luatexja-fontspec` + Fandol 显示中文。`RenderPolicy` 控制图表浮动、宽内容降级与 caption 位置：表格 `SCALE_FONT` 与长公式 `SCALE_DOWN` 由 `\fitbox` / `\fitmath` 执行。图块按 layout 来源绑定 `ResourceDocument` 中的嵌入图像，而不是按全局序号猜测；无法提取时输出可观察空框。表格按完整网格投影（含 rowSpan/colSpan）；非浮动表格使用 `\captionof`。带编号的公式用 `\tag` 保留源编号。书目条目合并为 `thebibliography`。每个内容块生成起始与结束 hypertarget（`<nodeId>` / `<nodeId>:end`）；图表锚点位于浮动环境内。`recover_render_anchors` 把两端插值为覆盖各页内容区的多 fragment。

- 模板：`templates/latex/generic-academic.tex`
- 资源提取：`pdf_pipeline.resource_store`
- 翻译层契约：[`schemas/translation-layer/schema.json`](../../schemas/translation-layer/schema.json)（0.2.0）
- 渲染文档契约：[`schemas/render-document/schema.json`](../../schemas/render-document/schema.json)（0.2.0）
- 资源契约：[`schemas/resources/schema.json`](../../schemas/resources/schema.json)
- M5 落地说明：[`.agents/notes/implemented/architecture/2026-09-08-m5-translation-rendering-pipeline.md`](../../.agents/notes/implemented/architecture/2026-09-08-m5-translation-rendering-pipeline.md)
- 审查修复：[`.agents/notes/implemented/bug-fix/2026-09-08-m5-review-repairs.md`](../../.agents/notes/implemented/bug-fix/2026-09-08-m5-review-repairs.md)

RenderComposer 把语义节点与译文合成为 RenderDocument；FIGURE 与 `CAPTION_OF` 标题绑定为同一浮动块，TABLE_CAPTION 可绑定到 `RenderTableBlock`。LaTeX Backend 只消费 RenderDocument。没有多渲染器接口；Typst 为未来扩展。
