# 版面恢复

[中文](./layout-recovery.md) | [English](./layout-recovery.en.md)

LayoutDocument 的恢复契约见 [`document-architecture.md`](document-architecture.md)（已冻结）；Evidence 适配边界见 [`../contracts/parser-adapter-contract.md`](../contracts/parser-adapter-contract.md)。当前态实现（M3，见 [Agent Note](../../.agents/notes/implemented/architecture/2026-09-05-m3-layout-recovery-engine.md)）：

```text
PhysicalDocument
  → EvidenceProvider.collect → EvidenceBundle → normalize（Phase 3.1）
  → band/column 检测：递归 XY-cut，图形先聚簇（Phase 3.3/3.4）
  → 按列文本分块 + 图形聚类
  → Region Fusion：候选 × 几何块加权收敛（Phase 3.2）
  → Caption Association → LayoutGroup（Phase 3.7）
  → Footnote Recovery → FOOTNOTE region（Phase 3.8）
  → ReadingFlowGraph + CONTINUATION 边（Phase 3.5/3.6）
  → LayoutDocument
```

要点：

- **确定性**：同输入字节产出逐字节相同的 LayoutDocument；所有 ID 由 source fingerprint 派生。
- **先结构后分块**：通栏行会桥接左右栏，band/column 检测必须发生在文本分块之前。
- **Evidence 是唯一外部输入通道**：第三方 parser 输出只以 `EvidenceBundle` 候选进入融合；provider 类型永不越过该边界。默认 ensemble 为确定性 `mock` / `docling-sim` / `grobid-sim`；真实 MinerU/Docling/GROBID adapter 以同一 Protocol 接入（录制 dump + 可选活服务），不改变默认 registry。
- **阅读主序由 band/column 驱动，列内仍按几何**：band 自上而下、列自左而右、列内 (y, x)（y 量化到 4pt）；continuation/caption/footnote 以 reason+confidence 边表达。没有文档级全局 `sort(y, x)`。
- **评估**：`tests/fixtures/layout-truth/`（阅读顺序片段 + 手核 `regions[]`）+ `pdf_pipeline.metrics`（IoU≥0.5 且标签一致的 Region Recall/Precision、pairwise / sequence accuracy）+ `tests/benchmark/test_layout_benchmark.py`。
