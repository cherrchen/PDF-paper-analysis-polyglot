# Layout Recovery

[中文](./layout-recovery.md) | [English](./layout-recovery.en.md)

The LayoutDocument recovery contract lives in [`document-architecture.md`](document-architecture.md) (frozen); the evidence adapter boundary is defined in [`../contracts/parser-adapter-contract.md`](../contracts/parser-adapter-contract.md). Current-state implementation (M3, see the [Agent Note](../../.agents/notes/implemented/architecture/2026-09-05-m3-layout-recovery-engine.en.md)):

```text
PhysicalDocument
  → EvidenceProvider.collect → EvidenceBundle → normalize (Phase 3.1)
  → band/column detection: recursive XY-cut, graphics clustered first (Phase 3.3/3.4)
  → per-column text blocking + figure clustering
  → Region Fusion: weighted convergence of candidates × geometric blocks (Phase 3.2)
  → Caption Association → LayoutGroup (Phase 3.7)
  → Footnote Recovery → FOOTNOTE regions (Phase 3.8)
  → ReadingFlowGraph + CONTINUATION edges (Phase 3.5/3.6)
  → LayoutDocument
```

Key points:

- **Determinism**: identical input bytes produce a byte-identical LayoutDocument; all IDs derive from the source fingerprint.
- **Structure before blocking**: full-width lines bridge the two columns, so band/column detection must run before text blocking.
- **Evidence is the only external input channel**: third-party parser output enters fusion exclusively as `EvidenceBundle` candidates; provider types never cross that boundary. The current provider is the deterministic `MockLayoutEvidenceProvider`; a real MinerU adapter plugs into the same Protocol.
- **Primary order is band/column-driven; within a column it is still geometric**: bands top-down, columns left-right, (y, x) inside a column (y quantized to 4pt). Continuation/caption/footnotes are edges with reason+confidence. There is no document-wide `sort(y, x)`.
- **Evaluation**: `tests/fixtures/layout-truth/` (ground truth) + `pdf_pipeline.metrics` (Region Recall / pairwise / sequence accuracy) + `tests/benchmark/test_layout_benchmark.py`.
