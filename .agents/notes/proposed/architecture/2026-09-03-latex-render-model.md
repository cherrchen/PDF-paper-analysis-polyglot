# Agent Note: LaTeX 渲染模型

Status: proposed

[中文](./2026-09-03-latex-render-model.md) | [English](./2026-09-03-latex-render-model.en.md)

## 问题

必须把 SemanticDocument 投影到 LaTeX，又不能让 TeX 命令泄漏进语义模型。

## 提案

在 SemanticDocument 与 `templates/latex/` 之间引入专用 render-model / LaTeX 投影层。模板负责呈现。投影负责结构。在真正采用第二个后端之前，不要做通用多渲染器 trait。

## 考虑过的替代方案

- 在 SemanticDocument 序列化器里拼 LaTeX 字符串会污染真源模型。
- 为一个后端做 Renderer trait 是臆测。

## 验收标准

- 语义类型不含必需的 TeX 字段，明确的原始源码捕获除外
- 一等模板能通过 `just latex-smoke` 编译
- 投影变更带有渲染测试

## 风险

模板过拟合单篇论文。全局 ChkTeX 抑制掩盖真实错误。
