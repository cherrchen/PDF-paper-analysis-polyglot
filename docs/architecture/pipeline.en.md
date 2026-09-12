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

From M7, the Evidence stage is adaptively routed by DocumentProbe + Capability Registry: `run_pipeline` probes first (`probe.json`), then selects the provider ensemble from the registry (layout primary, table/scholarly specialists), fuses per-provider evidence, and merges the bundle into semantic recovery. Current state: the [M7 landing note](../../.agents/notes/implemented/architecture/2026-09-12-m7-parser-ensemble.en.md). M8 v1 will turn those stages into resumable local workspace jobs; plan: [`docs/development/m8.en.md`](../development/m8.en.md). This page still describes one-shot `run_pipeline`.
