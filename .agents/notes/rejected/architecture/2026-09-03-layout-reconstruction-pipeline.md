# Agent Note: 版面重建流水线

Status: rejected — landed by later implemented notes; no longer current authority

[中文](./2026-09-03-layout-reconstruction-pipeline.md) | [English](./2026-09-03-layout-reconstruction-pipeline.en.md)

## 问题

学术 PDF 混合栏、图、脚注与公式。抽取到版面的路径尚未选定。

## 提案

把版面重建当作显式流水线阶段，输出 SemanticDocument，并与渲染分离。解析器与 OCR 引擎只在有依赖 Agent Note 之后才选定。

## 考虑过的替代方案

- 以渲染驱动重建（从 LaTeX 反推结构）会颠倒架构。
- 一次不透明的模型调用、没有版面阶段，会阻断确定性测试。

## 验收标准

- 流水线阶段有名称且可测
- 至少有单栏与重数学版面的夹具
- 不悄悄加入原生 PDF 库

## 风险

在没有隔离的情况下选择 PDFium/MuPDF/Poppler，会主导构建与许可证。
