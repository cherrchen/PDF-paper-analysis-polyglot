# Agent Note: Python / Rust 性能边界

Status: proposed

[中文](./2026-09-03-python-rust-performance-boundary.md) | [English](./2026-09-03-python-rust-performance-boundary.en.md)

## 问题

PDF 解析与版面在 Python 中可能过慢，但过早把太多东西搬进 Rust 会抬高 FFI 成本。

## 提案

编排、I/O 与 LLM 集成留在 Python。已证实的热点放进 `crates/`，经 `crates/bindings` 暴露。在 `benchmarks/` 下有测量之前，不要重写流水线。

## 考虑过的替代方案

- 全 Python 会推迟原生成本，但可能封顶吞吐。
- 全 Rust 会拖慢研究代码的迭代。
- 从 `apps/` 做临时 FFI 会藏起 bindings crate。

## 验收标准

- 重写前存在已测量的热点
- FFI 有唯一责任 crate
- 一份已落地 note 记录选定的切分

## 风险

过早的 FFI 复杂度。跨语言重复逻辑。
