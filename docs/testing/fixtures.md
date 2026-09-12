# 夹具

[中文](./fixtures.md) | [English](./fixtures.en.md)

只提交合成、自撰、公有领域或明确可再分发的文档。

优先：

```text
LaTeX source → latexmk / LuaLaTeX → PDF
```

每个非平凡夹具在 `tests/fixtures/metadata/` 中有元数据。语料清单见 [`tests/fixtures/pdf/README.md`](../../tests/fixtures/pdf/README.md)。

## Tier 1 合成语料

仓库内 Tier 1 benchmark 文档（13 篇），源文件位于 `tests/fixtures/source/latex/`：

```text
smoke                  — 单栏基线
two-column             — 普通双栏
spanning-figure        — 跨栏 Figure
table-heavy            — Table
equation-heavy         — Equation
footnote-multicolumn   — Footnote
bibliography           — Bibliography
cross-page-paragraph   — 跨页 Paragraph（短页单段落，强制跨页）
mixed-bands            — 全宽 band + 双栏
tikz-vector            — 复杂 Vector Figure
figure-caption         — 栅格 Figure + caption
paper-anatomy          — 论文解剖综合夹具（M4 Exit Gate：标题块、Abstract、嵌套 section、Figure、Table、编号 Equation、Footnote、Bibliography + 引用）
author-year-citations  — 作者-年引用（含 2020a 歧义后缀）
```

每个夹具在 `tests/fixtures/layout-truth/<name>.json` 有阅读顺序片段，以及手核后的 `regions[]`（`pageIndex` + `LayoutLabel` + canonical `geometry`，不用会漂移的 LayoutRegionID）。Region precision/recall 用 IoU≥0.5 且标签一致；不确定的区域不写入，避免把当前输出冻成 precision=1.0。

Native parser dump 夹具在 `tests/fixtures/parser-dumps/{mineru,docling,grobid}/`。`provenance.json` 把每份 dump 标为 `synthetic-contract` 或 `real-tool`；当前全部是合成契约夹具，不是 MinerU/Docling/GROBID 对真实 PDF 的录制。它们用于 adapter 契约与合成全链路（normalize / fusion / semantic），不进入默认 ensemble。契约覆盖 Docling-core v2.48 的 `coord_origin` / `table_cells` / 跨格 `grid`，以及 MinerU 多页公式 ID。GROBID 活路径用本地 HTTP stub 校验 multipart `input`，不启动 Java。真实工具验证缺口见 [M8 准入](m8.md)。

Tier 4 扫描 PDF 不提交进仓库；占位元数据见 `tests/fixtures/metadata/scanned-external.yaml`。

不要提交巨大的 PDF 语料。Git 历史必须保持精简。

命令：`just latex-smoke`（编译全部 fixture 源文件）。生成的 PDF 不入库。依赖这些 PDF 的测试在文件缺失时 `pytest.skip`，而不是崩溃。GitHub 的 Python job 会先编译夹具再跑 `just test-python` 与 `just benchmark`，因此 clean checkout 仍能执行管线、golden、覆盖率与质量回归门禁。
