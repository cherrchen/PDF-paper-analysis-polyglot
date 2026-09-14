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

From M7, the Evidence stage is adaptively routed by DocumentProbe + Capability Registry: `run_pipeline` probes first (`probe.json`), then selects the provider ensemble from the registry (layout primary, table/scholarly specialists), fuses per-provider evidence, and merges the bundle into semantic recovery. Current state: the [M7 landing note](../../.agents/notes/implemented/architecture/2026-09-12-m7-parser-ensemble.en.md). M8 batch A made `run_pipeline` resumable and batch B added job orchestration on top (file-backed queue + `flock` claims + per-stage failure attribution + manual retry): the commit/recovery contract plus job records and state machine are in [storage](storage.en.md), the HTTP endpoints in [HTTP API](api.en.md).
