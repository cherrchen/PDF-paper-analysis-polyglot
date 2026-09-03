# Agent Note: 源映射身份模型

Status: proposed

[中文](./2026-09-03-source-mapping-identity-model.md) | [English](./2026-09-03-source-mapping-identity-model.en.md)

## 问题

翻译与重建需要原 PDF、SemanticDocument 与渲染 PDF 之间的稳定关系。

## 提案

在实现之前先设计身份与映射规则（页面空间、阅读顺序、span ID、引用锚点）。把映射作为一等 SemanticDocument 数据持久化，而不是 LaTeX 注释。

## 考虑过的替代方案

- 只靠隐式顺序映射会在版面变化时断裂。
- 只把映射编码进生成的 LaTeX，会把语义绑死在一个渲染器上。

## 验收标准

- 有文档化的坐标系
- 抽取与渲染之间 ID 稳定
- 至少一个多元素夹具的测试

## 风险

不稳定的 ID 会使 golden 文件与翻译记忆失效。
