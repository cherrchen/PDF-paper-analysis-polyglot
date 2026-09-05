# Agent Note: M3 Review 修复

Status: implemented

[中文](./2026-09-05-m3-review-repairs.md) | [English](./2026-09-05-m3-review-repairs.en.md)

## 问题

2026-09-05 Code Review 发现 M3 Layout Recovery Engine 虽有完整模块，但 Exit Gate 标得过早：Tier-1 `twocolumn` 夹具正文太短，视觉上仍是单栏，`two-column.json` 甚至断言 `singleColumnOnly`；默认 CI 的双栏门禁落在 gitignore 的 arXiv PDF 上。页码进入 `primaryFlow`，`provenanceIds` 未写入 region，表题投影成 `FIGURE_CAPTION`，公式被标成 HEADING，`match_key` 与恒真断言是死代码。

本 Note 补充既有 [M3 Layout Recovery Engine 落地 Note](../architecture/2026-09-05-m3-layout-recovery-engine.md)，保留 XY-cut、mock Evidence 与结构驱动 reading flow，并修正完成依据。

## 决策

按原 Exit Gate 修复，不重做版面引擎，也不安装真实 MinerU：

1. 加长 `two-column` / `mixed-bands` / `footnote-multicolumn` / `spanning-figure` 夹具，使左栏填满、右栏出现可识别正文；`mixed-bands` 在 `\twocolumn[...]` 可选参数内留出全幅 skip，保证同一页有 `FULL_WIDTH` 与 `MULTI_COLUMN`，通栏图在下一页为 `SPANNING`。
2. Ground truth 增加 `expectMultiColumn`；benchmark 断言至少一页 `layoutMode == MULTI_COLUMN` 且两列。BERT / Attention 真实论文测试标 `@pytest.mark.slow`，默认 CI 不依赖外部 PDF。
3. 页脚条带放宽到页高 85%，短数字页码即使字号接近正文也标为 FOOTER；脚注标记行不并入上一块。
4. 融合后的 `LayoutRegion.provenanceIds` 写入对应 `ProvenanceRecord`；`TABLE_BLOCK` 投影为 `TABLE_CAPTION`；`_is_heading_like` 拒绝含 `=` 的公式形态；正文 `body_font` 在家具分离后重算。
5. `NormalizedCandidate.match_key()` 作为 fusion 的可观测 co-location 信号；孤儿列按 y 重叠选 band；切栏前丢弃厚度不足 2pt 的装饰线；列内阅读序对 y 做 4pt 量化，避免同行左右颠倒。
6. Region Precision 只对非空 `primaryFlow` 文本 region 计算，不设虚假高门槛。脚注 reference evidence 留 M4。

## 考虑过的替代方案

- 保持 M3「已完成」并把双栏门禁留在外部 PDF：CI 在 clean checkout 无法复现 Exit Gate。
- 把 XY-cut 换成全页投影或「先读完整左栏再读右栏、合并相邻 MULTI_COLUMN」：会推翻已落地的结构检测决策；本轮只修夹具与排序抖动。
- 安装真实 MinerU 以撑起 precision：重型依赖与不可复现环境仍不成立；snippet 级 GT 撑不起区域级 precision。

## 后果

- M3 Exit Gate 在审查修复后关闭：合成夹具承担双栏 / 通栏 / 脚注门禁；benchmark recall ≥ 0.9、pairwise ≥ 0.95、sequence 全对。
- smoke golden 有意变更：公式不再是 HEADING，页码退出语义树。
- 已知限制更新见 M3 落地 note：Region Precision 待区域级标注；reference evidence 仍属 M4。
