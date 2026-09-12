# Agent Note: 区域级标注真值

Status: implemented

[中文](./2026-09-12-region-level-layout-truth.md) | [English](./2026-09-12-region-level-layout-truth.en.md)

## 问题

M7 的 Region Precision 与数值校准一直用 `readingOrder` 片段冒充区域命中：未写入片段的 recovered region 无法当负例，`paragraphRecoveryAccuracy` / `sectionHierarchyAccuracy` 恒为 null。这与用户 Annotation 层不是同一件事；PRD §47 明确初版不做 Annotation。

## 决策

1. **`layout-truth.regions[]` 是 benchmark 真值，不是 Annotation 层。** 每条记录 `pageIndex`、`LayoutLabel`、canonical `geometry`、可选 `textPreview`。不用会漂移的 `LayoutRegionID`。保留 `readingOrder` 作顺序回归。
2. **匹配规则：** IoU ≥ 0.5 且标签一致（看 `region.labels[0].label`，不是 `kind`）。HEADER/FOOTER 不计入 recovered 集合。不确定的框不写入，禁止把当前输出冻成 precision=1.0。
3. **有标签后：** `quality_report` 用 labeled metrics；`paragraphRecoveryAccuracy` / `sectionHierarchyAccuracy` 分别对 `PARAGRAPH_LIKE` / `HEADING_LIKE` 计算。校准样本改为 fused confidence vs IoU 命中。
4. **校准仍是 diagnostic。** 不再以「真值太稀」为豁免理由；它审计融合公式，不是产品门禁。`compare()` 不把校准准确率标成 `REGRESSED`。见 [M7 落地 note](./2026-09-12-m7-parser-ensemble.md) 决策 10 的当时口径，本 note 取代其「区域级真值尚未存在」的前置。
5. **baseline 更新走 golden 政策。** 真值粒度变化会改数字；提交须说明理由，禁止为了转绿盲改。

## 考虑过的替代方案

- 把 Annotation 层做成 Viewer 批注并当 GT：违反 PRD §47 / 无 `FR-ANN-*`。
- 用片段匹配继续冒充 precision：无法校准，也无法区分漏检与过检。
- 把当前 recovery 全量冻进 `regions[]`：precision 恒 1.0，失去回归意义。

## 后果

- 夹具约定见 [`docs/testing/fixtures.md`](../../../../docs/testing/fixtures.md)；draft 脚本 `scripts/seed_layout_truth_regions.py` 只导出 snippet 命中与 FIGURE/TABLE/FORMULA。
- `author-year-citations` 补齐 layout-truth。
- `tests/benchmark/baseline.json` 因真值粒度从片段改为 IoU+标签而更新：旧 regionRecall=1.0 是 snippet 命中，不是区域精度；新数字更低但是诚实门禁。`paragraphRecoveryAccuracy` / `sectionHierarchyAccuracy` 从 null 变为可测。校准仍是 diagnostic。
- 本决策补充 [PRD 过滤 roadmap 延期项](../process/2026-09-12-prd-filters-roadmap-deferrals.md)，不改写 M7 历史决策句。
