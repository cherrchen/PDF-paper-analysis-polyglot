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
- Engine policy: `tex/README.md` and [`docs/development/latex.md`](../development/latex.en.md)
- LaTeX backend decision: [`.agents/notes/implemented/architecture/2026-09-03-latex-as-initial-rendering-backend.en.md`](../../.agents/notes/implemented/architecture/2026-09-03-latex-as-initial-rendering-backend.en.md)
- Document Architecture v0.1: [`.agents/notes/implemented/architecture/2026-09-03-document-architecture.en.md`](../../.agents/notes/implemented/architecture/2026-09-03-document-architecture.en.md)

LaTeX Backend consumes Render IR only; it does not generate publisher-specific LaTeX directly from SemanticDocument. There is no multi-renderer interface; Typst is a future extension.
