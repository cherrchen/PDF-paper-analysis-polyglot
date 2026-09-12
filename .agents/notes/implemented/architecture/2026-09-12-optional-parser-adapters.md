# Agent Note: 可选真实 parser 依赖

Status: implemented

[中文](./2026-09-12-optional-parser-adapters.md) | [English](./2026-09-12-optional-parser-adapters.en.md)

## 问题

PRD §34 要求 MinerU / Docling / GROBID 作为 Evidence Provider，但依赖策略禁止默认安装重型原生库与不可复现模型。CI 也不能下载数 GB 权重或启动 Java 服务。

## 决策

1. **默认安装不变。** `pdf-pipeline` 运行时仍只有 `pypdfium2`。默认 capability registry 仍是 `mock` / `docling-sim` / `grobid-sim`。
2. **真实 adapter 是 dump 映射器。** `pdf_pipeline.evidence.mineru` / `docling` / `grobid` 实现 `EvidenceProvider`，把录制的 native JSON/TEI 映射为 `EvidenceBundle`。CI 夹具在 `tests/fixtures/parser-dumps/`。第三方 schema 不得泄漏。
3. **活服务可选、环境驱动。** `MINERU_CMD` / `DOCLING_CMD` 对 `PAPER_SOURCE_PDF` 产出 JSON；`GROBID_URL` 对同一 PDF 做 HTTP POST。未配置则 `collect()` 失败并说明如何提供 dump。`pdf-pipeline` 的 `[mineru]` / `[docling]` / `[grobid]` extras 仅为分组名，不把 MinerU/Docling/Torch/GROBID 写进 lockfile 或必选依赖。
4. **升级仍走 roadmap §11。** 把 registry primary 换成 `mineru`/`docling`/`grobid` 必须经过 benchmark，禁止因为 adapter 存在就替换 production provider。

## 考虑过的替代方案

- 把 MinerU/Docling/GROBID 装进默认依赖：违反重型原生库需 Agent Note 的可复现约束，CI 不可运行。
- 只保留 sim、不写 native 映射：PRD §34 的 adapter 边界无法在不装模型的情况下被测试。

## 后果

- `build_provider("mineru"|"docling"|"grobid")` 可实例化；默认 `route_providers` 仍选出 sim 名。
- 活路径是本机实验，不是 CI 门禁。
