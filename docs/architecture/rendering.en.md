# Rendering

[中文](./rendering.md) | [English](./rendering.en.md)

Rendering architecture: [`document-architecture.en.md`](document-architecture.en.md) sections 25–32.

Live path (M5):

```text
SemanticDocument
+
TranslationLayer
      ↓
compose_render_document(semantic, translation, profile, policy, resources)
      ↓
RenderDocument  (HEADING / PARAGRAPH / FIGURE / TABLE / EQUATION / BIBLIOGRAPHY)
      ↓
LaTeX Backend  (generic-academic.tex + profile parameters)
      ↓
LuaLaTeX
      ↓
PDF
```

The default profile is `readable-single-column` (A4, 11pt, 1.25 line spacing, single column). `RenderPolicy` controls float behavior, wide-content degradation, and caption placement. Figure blocks may reference embedded images from `ResourceDocument`; tables and equations use `tabular` / `equation` environments; bibliography entries are merged into `thebibliography`. Each content block emits start and end hypertargets (`<nodeId>` / `<nodeId>:end`); `recover_render_anchors` recovers multi-fragment anchors.

- Template: `templates/latex/generic-academic.tex`
- Resource extraction: `pdf_pipeline.resource_store`
- Translation contract: [`schemas/translation-layer/schema.json`](../../schemas/translation-layer/schema.json) (0.2.0)
- Render-document contract: [`schemas/render-document/schema.json`](../../schemas/render-document/schema.json) (0.2.0)
- Resources contract: [`schemas/resources/schema.json`](../../schemas/resources/schema.json)
- M5 landing note: [`.agents/notes/implemented/architecture/2026-09-08-m5-translation-rendering-pipeline.en.md`](../../.agents/notes/implemented/architecture/2026-09-08-m5-translation-rendering-pipeline.en.md)

RenderComposer combines semantic nodes and translated content into a RenderDocument; a figure and its `CAPTION_OF` caption share one float block, and a `TABLE_CAPTION` may bind to `RenderTableBlock`. The LaTeX backend consumes RenderDocument only. There is no multi-renderer interface; Typst remains a future extension.
