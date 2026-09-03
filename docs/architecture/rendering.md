# 渲染

[中文](./rendering.md) | [English](./rendering.en.md)

当前渲染路径：

```text
SemanticDocument
      ↓
LaTeX projection
      ↓
LuaLaTeX
      ↓
PDF
```

- 模板：`templates/latex/`
- 引擎策略：`tex/README.md` 与 [`docs/development/latex.md`](../development/latex.md)
- 决策：[`.agents/notes/implemented/architecture/2026-09-03-latex-as-initial-rendering-backend.md`](../../.agents/notes/implemented/architecture/2026-09-03-latex-as-initial-rendering-backend.md)

没有多渲染器接口。render-model 形态未决：[`.agents/notes/proposed/architecture/2026-09-03-latex-render-model.md`](../../.agents/notes/proposed/architecture/2026-09-03-latex-render-model.md)。
