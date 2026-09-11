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

自 M7 起，Evidence 阶段由 DocumentProbe + Capability Registry 驱动自适应路由：`run_pipeline` 先探测（`probe.json`），再按 registry 选出 provider ensemble（layout 主 provider、表格/学术 specialist），逐 provider 归属进融合，合并 bundle 进语义恢复。当前态见 [M7 落地 note](../../.agents/notes/implemented/architecture/2026-09-12-m7-parser-ensemble.md)。
