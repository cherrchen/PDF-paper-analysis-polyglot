# Rendering

[中文](./rendering.md) | [English](./rendering.en.md)

Current rendering path:

```text
SemanticDocument
      ↓
LaTeX projection
      ↓
LuaLaTeX
      ↓
PDF
```

- Templates: `templates/latex/`
- Engine policy: `tex/README.md` and [`docs/development/latex.md`](../development/latex.en.md)
- Decision: [`.agents/notes/implemented/architecture/2026-09-03-latex-as-initial-rendering-backend.md`](../../.agents/notes/implemented/architecture/2026-09-03-latex-as-initial-rendering-backend.en.md)

There is no multi-renderer interface. The render-model shape is unresolved: [`.agents/notes/proposed/architecture/2026-09-03-latex-render-model.md`](../../.agents/notes/proposed/architecture/2026-09-03-latex-render-model.en.md).
