# Golden 测试

[中文](./golden.md) | [English](./golden.en.md)

期望的 SemanticDocument 输出位于 `tests/golden/<fixture>/document.json`。

比较前先规范化。避免非确定顺序。

禁止仅为让失败测试闭嘴而更新 golden。先判定：

1. 实现是错的，或
2. 期望契约有意变更

只有 (2) 才允许 `just test-update-golden`。提交前审阅 diff。
