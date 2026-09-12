# Agent Note: PRD 过滤 roadmap 延期项

Status: implemented

[中文](./2026-09-12-prd-filters-roadmap-deferrals.md) | [English](./2026-09-12-prd-filters-roadmap-deferrals.en.md)

## 问题

M7 基线落地后，roadmap「建议下一步」把一串延期项绑成进入 M8 的前置：真实 MinerU/Docling/GROBID adapter、区域级标注真值、`source-derived` / `dense-two-column` profile、MathML、矢量图 PDF/SVG、字符级 mapping、annotation 层。其中若干项与 PRD v0.2 的 Initial Product 边界冲突或根本不是 FR。[产品需求文档 v0.2](./2026-09-06-product-requirements-v02.md) 已规定下游以 PRD 为上游；若不显式剔除，Milestone 会把 Post-Initial / NG 当成欠债。

## 决策

1. **PRD v0.2 过滤延期清单。** Roadmap 里「进入 M8 前必须做完」不得包含 NG、Post-Initial（§44「不属于当前 Milestone 的强制验收要求」）或未点名的编码细节。本 note 裁定表是该过滤的权威记录；当前态见 [`docs/development/roadmap.md`](../../../../docs/development/roadmap.md)。
2. **从延期清单删除（非 Initial Product）：**
   - 字符级 mapping — [PRD NG4](../../../../docs/product/requirements.md)、FR-SYNC-005、§43「Character Mapping：不要求」。身份与同步保持 SemanticNode；`SourceFragment` 仍仅 `LayoutRegionRef`。
   - `source-derived` / `dense-two-column` — FR-LAYOUT-004 默认单栏；§43「是否继承原双栏：初版不要求」；R2 为 Post-Initial。默认仍是 `readable-single-column`。延续 v0.2 note 对 `SourceDerivedProfile` 的裁定。
   - Annotation 层 — PRD §47 未来扩展；§43 SemanticDocument 用户编辑初版不支持。没有 `FR-ANN-*`。区域级**标注真值**（benchmark ground truth）不是 Annotation 派生层。
   - MathML 作为独立延期交付 — FR-EQ-002 要求可重排数学表示，未点名 MathML。`latex` / `unicodeText` / `rawText` 覆盖初版；schema 的 `mathml` 字段保留，adapter 若产出则拷贝，不单独立项。
3. **进入 M8 前仍须收口（与 PRD 一致）：**
   - 真实 MinerU / Docling / GROBID adapter — PRD §34；第三方只出 Evidence。默认 CI 走录制 dump；活服务为可选 extras。默认 capability registry 仍是 `mock` / `docling-sim` / `grobid-sim`。
   - 区域级标注真值 — M7 Region Precision 与数值校准的工程前置，不是用户 Annotation。
   - 矢量 Figure 的 PDF fragment — FR-FIG-001 / FR-FIG-005 / §43「Asset 保持原图」。SVG 真源不是 FR，不做交付。
4. **不改写历史落地 note。** M5/M6/M7 已落地 note 里「当时延期」的句子保持原样，只交叉链接到本 note。当前态文档与 roadmap 进度段改写为裁定后的事实。

## 考虑过的替代方案

- 把 roadmap 原延期清单全部实现后再进 M8：会把 NG4、R2、§47 当成初版验收，违反 PRD 上游约束。
- 只改「建议下一步」一句、明细仍写「未实现字符级 / MathML」：欠债语义仍在，Agent 会继续当作必须项。
- 把 MathML / SVG 当成 FR-EQ / FR-FIG 的隐含要求：PRD 要的是可重排公式与保持原图，LaTeX + PDF fragment 已覆盖；点名编码不是需求。

## 后果

- 进入 M8 的前置收窄为三项 PRD 对齐缺口；落地见 [可选真实 parser 依赖](../architecture/2026-09-12-optional-parser-adapters.md)、[区域级标注真值](../architecture/2026-09-12-region-level-layout-truth.md)、[Figure PDF fragment](../architecture/2026-09-12-figure-pdf-fragment.md)。正确性收口见 [M8 前审查修复](../bug-fix/2026-09-12-m8-pre-review-repairs.md)，不以错误的语义准确率名称作为验收证据。
- 相关当前态页不再把字符级 mapping、双栏 profile、Annotation 层、独立 MathML 写成「尚未实现的欠债」。
- 本决策补充而非取代 [产品需求文档 v0.2](./2026-09-06-product-requirements-v02.md)。
