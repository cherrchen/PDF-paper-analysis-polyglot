# Agent Note: M8 前审查正确性修复

Status: implemented

[中文](./2026-09-12-m8-pre-review-repairs.md) | [English](./2026-09-12-m8-pre-review-repairs.en.md)

## 问题

进入 M8 前的代码审查（2026-09-12）认定：主干回归通过，但新增功能仍有可复现正确性问题，不能把「M8 前缺口已全部收口」当成验收结论。Figure 投影同时输出 PDF fragment 与嵌入位图；Docling `l/t/r/b` 忽略 `coord_origin`，BOTTOMLEFT 高度为负后被丢掉；`grid` 把合并单元格重复展开；MinerU 公式 ID 只有页内 `block_index`，跨页冲突；GROBID 活路径用 `application/pdf` 直 POST，不符合 `processFulltextDocument` 的 multipart `input`；`paragraphRecoveryAccuracy` / `sectionHierarchyAccuracy` 实际是 Layout 标签召回。本 note 补充 [M7 落地](../architecture/2026-09-12-m7-parser-ensemble.md)、[可选真实 parser](../architecture/2026-09-12-optional-parser-adapters.md)、[区域级标注真值](../architecture/2026-09-12-region-level-layout-truth.md)、[Figure PDF fragment](../architecture/2026-09-12-figure-pdf-fragment.md)，不改写其历史决策句。

## 决策

1. **Figure 投影只选一种表示。** `FigureResource` 仍同时保留 `pdfFragmentResourceId` 与 `embeddedImageIds`。`figure_resource_ids` 在可用集合上选择：有 fragment 则只投影 fragment，否则投影位图；多位图且无 fragment 时仍堆叠并记 Issue。不能只靠列表排序。
2. **Docling 坐标进 canonical。** `parse_rect` 对 `l/t/r/b` 读取 `coord_origin`；BOTTOMLEFT 用页面高度翻到 top-left（与仓库 canonical 一致）；两种原点都覆盖。
3. **合并单元格去重。** 优先消费 Docling `table_cells` 的 start/end offset；仅有 `grid` 时按 span 原点去重，禁止按网格位置重复创建跨列单元格。
4. **公式 ID 含页标识。** MinerU `derived_id` 使用 `formula-{pageId}-{block_index}`，并加两页回归。
5. **GROBID 活请求符合接口。** `POST /api/processFulltextDocument` 使用 `multipart/form-data`，PDF 放在 `input` 字段。本地 HTTP stub 校验路径、头与请求体。
6. **指标改用准确名称。** `paragraphLabelRecall` / `headingLabelRecall` 是 `PARAGRAPH_LIKE` / `HEADING_LIKE` 区域召回；不检查段落合并/拆分、heading level 或章节父子。`semanticExpectationCoverage` 仍只是 kinds / minCounts。这些数字不能当语义能力收口证据。baseline 键随契约更名，数值不变。
7. **契约测试优先于自制单页 happy path。** 夹具按 Docling-core v2.48 字段（`coord_origin`、`table_cells`、跨格 `grid`）与 MinerU 多页 `pdf_info` 录制；活路径用 HTTP stub，不启动 Java/模型。
8. **质量整理。** dump/进程 I/O 收到 `native.py`；同一 PDF 只打开一次再裁 fragment；adapter 文件不再用文件级 pyright 豁免（JSON 边界留在 `native.py`）。

## 考虑过的替代方案

- 只把 fragment 排到 `resourceIds` 前面仍全部投影：审查已用 `figure-caption` 复现双 `includegraphics`。
- 对 BOTTOMLEFT 只取 `abs(b-t)`：高度为正，但 y 仍停在 PDF 顶边，框会落到页面错误一侧。
- 继续遍历 `grid` 并用 `row`/`column` 字段：Docling 会在跨度覆盖位置重复同一 cell，第二个 `colSpan=2` 越界。
- 补真正的段落/章节语义真值再保留旧指标名：超出本轮范围；错误名称会继续把 layout 召回当成语义准确率。

## 后果

- 当前态：[`docs/architecture/rendering.md`](../../../../docs/architecture/rendering.md)、[`docs/development/roadmap.md`](../../../../docs/development/roadmap.md) 7.6 / 4.3、[`docs/contracts/parser-adapter-contract.md`](../../../../docs/contracts/parser-adapter-contract.md)、[`docs/testing/fixtures.md`](../../../../docs/testing/fixtures.md)。
- 三项 PRD 表面（真实 adapter、区域真值、PDF fragment）仍在，但本轮正确性修复完成前不得把「已全部收口」写成 M8 准入。准入分级与初版计划见 [M8 准入收口](../process/2026-09-12-m8-admission-closeout.md)。
- baseline 键更名走 golden 政策：同一数字、新名称，理由是停止把标签召回叫成语义准确率。
