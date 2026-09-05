# 夹具

[中文](./fixtures.md) | [English](./fixtures.en.md)

只提交合成、自撰、公有领域或明确可再分发的文档。

优先：

```text
LaTeX source → latexmk / LuaLaTeX → PDF
```

每个非平凡夹具在 `tests/fixtures/metadata/` 中有元数据。语料清单见 [`tests/fixtures/pdf/README.md`](../../tests/fixtures/pdf/README.md)。

## Tier 1 合成语料

仓库内首批 10 篇 Tier 1 benchmark 文档，源文件位于 `tests/fixtures/source/latex/`：

```text
smoke                  — 单栏基线
two-column             — 普通双栏
spanning-figure        — 跨栏 Figure
table-heavy            — Table
equation-heavy         — Equation
footnote-multicolumn   — Footnote
bibliography           — Bibliography
cross-page-paragraph   — 跨页 Paragraph
mixed-bands            — 全宽 band + 双栏
tikz-vector            — 复杂 Vector Figure
```

Tier 4 扫描 PDF 不提交进仓库；占位元数据见 `tests/fixtures/metadata/scanned-external.yaml`。

不要提交巨大的 PDF 语料。Git 历史必须保持精简。

命令：`just latex-smoke`（编译全部 fixture 源文件）。生成的 PDF 不入库。依赖这些 PDF 的测试在文件缺失时 `pytest.skip`，而不是崩溃。GitHub 的 Python job 会先编译夹具再跑 `just test-python`，因此 clean checkout 仍能执行管线、golden 与覆盖率门禁。
