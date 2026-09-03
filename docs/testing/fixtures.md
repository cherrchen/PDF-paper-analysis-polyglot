# 夹具

[中文](./fixtures.md) | [English](./fixtures.en.md)

只提交合成、自撰、公有领域或明确可再分发的文档。

优先：

```text
LaTeX source → latexmk / LuaLaTeX → PDF
```

每个非平凡夹具在 `tests/fixtures/metadata/` 中有元数据。

不要提交巨大的 PDF 语料。Git 历史必须保持精简。

命令：`just latex-smoke`。
