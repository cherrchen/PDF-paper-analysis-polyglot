# 渲染

[中文](./rendering.md) | [English](./rendering.en.md)

渲染架构见 [`document-architecture.md`](document-architecture.md) 第 25–32 节。

当前渲染路径：

```text
SemanticDocument
+
TranslationLayer
+
RenderProfile
+
RenderPolicy
      ↓
RenderComposer
      ↓
RenderDocument
      ↓
LaTeX Backend
      ↓
LuaLaTeX
      ↓
PDF
```

- 模板：`templates/latex/`
- 翻译层契约：[`schemas/translation-layer/schema.json`](../../schemas/translation-layer/schema.json)
- 渲染文档契约：[`schemas/render-document/schema.json`](../../schemas/render-document/schema.json)
- 引擎策略：`tex/README.md` 与 [`docs/development/latex.md`](../development/latex.md)
- LaTeX 后端决策：[`.agents/notes/implemented/architecture/2026-09-03-latex-as-initial-rendering-backend.md`](../../.agents/notes/implemented/architecture/2026-09-03-latex-as-initial-rendering-backend.md)
- 文档架构 v0.1：[`.agents/notes/implemented/architecture/2026-09-03-document-architecture.md`](../../.agents/notes/implemented/architecture/2026-09-03-document-architecture.md)

RenderComposer 把语义节点、可选译文、profile 与 policy 合成为 RenderDocument；图像与 `CAPTION_OF` 标题在此阶段绑定为同一个渲染块。LaTeX Backend 只消费 RenderDocument，不直接从 SemanticDocument 生成出版社特定 LaTeX。没有多渲染器接口；Typst 为未来扩展。
