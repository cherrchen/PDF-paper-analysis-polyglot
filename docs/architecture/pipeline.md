# 流水线

[中文](./pipeline.md) | [English](./pipeline.en.md)

完整流水线定义见 [`document-architecture.md`](document-architecture.md) 第 1、9、42、50 节。

```text
PDF → PhysicalDocument → Evidence → LayoutDocument
    → SemanticDocument → Derived Layers → RenderComposer
    → RenderDocument → LaTeX → Target PDF
```

语言分工与 package 布局见 [`document-architecture.md`](document-architecture.md) 第 44–45 节。

Python / Rust 性能边界见同文档第 45 节与已落地 note [`.agents/notes/implemented/architecture/2026-09-03-document-architecture.md`](../../.agents/notes/implemented/architecture/2026-09-03-document-architecture.md)。
