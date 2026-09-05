# Golden 测试

[中文](./golden.md) | [English](./golden.en.md)

期望的 SemanticDocument 输出位于 `tests/golden/<fixture>/semantic.json`。

比较前先规范化。避免非确定顺序。夹具 PDF 由各环境的 `just latex-smoke` 生成，字节并不跨 TeX 安装相同；由 PDF 指纹派生的不透明 ID 在比较前重映射。Golden 锁定节点种类、文本、树形与非 ID 属性，而不是不透明标识符。`smoke` 只保留跨 TeX / PDFium 抽取稳定的字符串；`\int` 一类字形放在 `equation-heavy`。

禁止仅为让失败测试闭嘴而更新 golden。先判定：

1. 实现是错的，或
2. 期望契约有意变更

只有 (2) 才允许 `just test-update-golden`。提交前审阅 diff。
