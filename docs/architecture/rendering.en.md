# Rendering

[中文](./rendering.md) | [English](./rendering.en.md)

Rendering architecture: [`document-architecture.en.md`](document-architecture.en.md) sections 25–32.

Current rendering path:

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

- Templates: `templates/latex/`
- Translation contract: [`schemas/translation-layer/schema.json`](../../schemas/translation-layer/schema.json)
- Render-document contract: [`schemas/render-document/schema.json`](../../schemas/render-document/schema.json)
- Engine policy: `tex/README.md` and [`docs/development/latex.md`](../development/latex.en.md)
- LaTeX backend decision: [`.agents/notes/implemented/architecture/2026-09-03-latex-as-initial-rendering-backend.en.md`](../../.agents/notes/implemented/architecture/2026-09-03-latex-as-initial-rendering-backend.en.md)
- Document Architecture v0.1: [`.agents/notes/implemented/architecture/2026-09-03-document-architecture.en.md`](../../.agents/notes/implemented/architecture/2026-09-03-document-architecture.en.md)

RenderComposer combines semantic nodes, optional translated content, profile, and policy into a RenderDocument; it also binds a figure and its `CAPTION_OF` caption into one render block. The LaTeX Backend consumes RenderDocument only. It does not generate publisher-specific LaTeX directly from SemanticDocument. There is no multi-renderer interface; Typst remains a future extension.
