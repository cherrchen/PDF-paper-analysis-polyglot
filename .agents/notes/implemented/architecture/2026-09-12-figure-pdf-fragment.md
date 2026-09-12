# Agent Note: Figure PDF fragment 原图

Status: implemented

[中文](./2026-09-12-figure-pdf-fragment.md) | [English](./2026-09-12-figure-pdf-fragment.en.md)

## 问题

无嵌入位图的矢量 Figure（如 `tikz-vector`）在 M5 资源提取后变成空 `\fbox`。FR-FIG-001 / FR-FIG-005 / PRD §43 要求恢复或裁剪 Figure 资源并保持原图。SVG 真源不是 FR。

## 决策

1. **按 Figure 区域 bbox 裁剪源 PDF 页** 为 `PDF_FRAGMENT`（`ResourceKind` 已有）。绑定 `FigureResource.pdfFragmentResourceId`；已有 `embeddedImageIds` 保留。
2. **投影顺序：** PDF fragment → 嵌入位图 → 空框 Issue。LaTeX 用已有 `graphicx` 引用 `.pdf`。**不做 SVG 导出。** `VectorObject` 仍可只存几何；资产真源是页裁剪 PDF。
3. **不新增 TeX 宏包。** `rerender_workspace` 消费已写入的 `resources.json`，不再裁剪（FR-TRANS-004 零源重解析）。

## 考虑过的替代方案

- 把 path 转成 SVG 当真源：不是 FR，增加渲染后端与字体问题。
- 仅栅格化矢量图：损失矢量，违反「Asset 保持原图」。
- 空框继续当可观察失败：无法满足 FR-FIG-001。

## 后果

- `tikz-vector` 编译出 `\includegraphics{...pdf}`；`figure-caption` 位图仍提取并绑定。
- 当前态见 [`docs/architecture/rendering.md`](../../../../docs/architecture/rendering.md)。
- 本决策兑现 [PRD 过滤 roadmap 延期项](../process/2026-09-12-prd-filters-roadmap-deferrals.md) 的 FR-FIG 收口，不引入多渲染器。
