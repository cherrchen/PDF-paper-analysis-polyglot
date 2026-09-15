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

自 M7 起，Evidence 阶段由 DocumentProbe + Capability Registry 驱动自适应路由：`run_pipeline` 先探测（`probe.json`），再按 registry 选出 provider ensemble（layout 主 provider、表格/学术 specialist），逐 provider 归属进融合，合并 bundle 进语义恢复。当前态见 [M7 落地 note](../../.agents/notes/implemented/architecture/2026-09-12-m7-parser-ensemble.md)。M8 批次 A 已使 `run_pipeline` 支持恢复，批次 B 已在其上加 Job 编排（文件式队列 + `flock` 认领 + 阶段归因失败 + 手动重试），批次 C 已把阶段缓存键补齐为「producer 版本 + 上游产物哈希 + 阶段配置（registry / parser dump / 翻译配置 / 渲染模板 / schema 与 pipeline 版本）」并提供显式局部重跑（`rerun_from` / `--rerun-from`）与源重绑（`accept_source_change` / `--accept-source-change`）；批次 D 把 evidence specialist 的失败隔离为 capability 级降级——provider 异常不再打断阶段，而是记一条归属该 provider 的 `ERROR` Issue、写 `probe.json.degradations`、由 registry `fallback` 或内建基线顶替该 capability，并把 EVIDENCE 提交为 `degraded`（产物照常发布、下游继续，下次运行重跑该阶段）；只有所有 routed provider 全失败才让 EVIDENCE 真失败。批次 E 补上 parser 配置入口：Evidence 路由默认仍用内置 sim registry，可用 `PAPER_CAPABILITY_REGISTRY` 或 CLI `--registry` 指向同形状 TOML 覆盖（优先级 flag > env > 内置），**实际使用的 registry 字节**参与 EVIDENCE/LAYOUT 缓存键，因此换 parser 只改配置即让那两个阶段失效；配置不可读时不回退到内置 registry，而是明确报 `CapabilityRegistryError`。当前提交与恢复契约、缓存键、失效传播与降级语义见 [存储](storage.md)，HTTP 端点见 [HTTP API](api.md)。
