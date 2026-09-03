# Pipeline

[中文](./pipeline.md) | [English](./pipeline.en.md)

Full pipeline definition: [`document-architecture.en.md`](document-architecture.en.md) sections 1, 9, 42, and 50.

```text
PDF → PhysicalDocument → Evidence → LayoutDocument
    → SemanticDocument → Derived Layers → RenderComposer
    → RenderDocument → LaTeX → Target PDF
```

Language allocation and package layout: [`document-architecture.en.md`](document-architecture.en.md) sections 44–45.

Python / Rust performance boundary: same document section 45 and implemented note [`.agents/notes/implemented/architecture/2026-09-03-document-architecture.en.md`](../../.agents/notes/implemented/architecture/2026-09-03-document-architecture.en.md).
