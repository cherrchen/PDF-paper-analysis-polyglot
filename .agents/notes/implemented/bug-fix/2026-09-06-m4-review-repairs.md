# Agent Note: M4 Review 修复

Status: implemented

[中文](./2026-09-06-m4-review-repairs.md) | [English](./2026-09-06-m4-review-repairs.en.md)

## 问题

2026-09-06 Code Review 发现 M4 Semantic Recovery Engine 模块齐全、`paper-anatomy` 也能恢复十类结构，但 Exit Gate 标得过早。具名跨页夹具实际只有一页且是两段 TeX 段落；layout 侧把 author→date 的 CONTINUATION 当成跨页证据；语义侧要求 `mergedParagraphNodes: 0`。FigureResource 把 PhysicalObjectID 写入 ResourceID。`FOOTNOTE_REFERENCE` 在 M2 冻结后仍按「冻结前 PATCH」留在 `0.1.0`。`[1-3]` 引用区间不展开。若干测试验错对象或不断言 Abstract / 章节嵌套。路线图把 GROBID / 结构化表标成 Done。

本 Note 补充既有 [M4 Semantic Recovery Engine 落地 Note](../architecture/2026-09-06-m4-semantic-recovery-engine.md)，不重做语义引擎，也不安装真实 GROBID / MinerU。

## 决策

按原 Exit Gate 与 Review C 修复完成依据：

1. 重写 `cross-page-paragraph` 为短页单段落，强制跨页；layout benchmark 断言**跨页** CONTINUATION；语义 benchmark 要求 merge 与多 fragment anchor。
2. `FigureResource.embeddedImageIds` 保持空列表，直到存在 ResourceStore；禁止把 PhysicalObjectID 当作 ResourceID。
3. 记录 schema 冻结例外：M2 之后兼容性冻结已生效；`FOOTNOTE_REFERENCE` 是 MINOR 级 additive enum，当时未升版本。后续 additive 能力必须按 MINOR 升级。更新 `docs/contracts/` 冻结表述。
4. 引用区间 `[1-3]` / `[1–3]` 展开为闭区间；未解析与重复条目有测试。
5. 脚注支持符号 marker；docstring 与 PDFium「上标前插入空格」的行为对齐，不再假装 letter-glue。空 FOOTNOTE region 仍建节点并记 Issue。
6. SemanticValidator 按文档树序检查 heading level 跳变；TABLE_CAPTION 缺失关系归 `TABLE_RECOVERY`；非 CITES 的 dangling 目标归 `SOURCE_MAPPING`。
7. 修弱测试：层分离检查 layout↔semantic；bundle 引用使用真实 SourceAnchor；确定性比较含 `lines=`；benchmark 断言 `frontMatterRoles` 与 `sectionParentOf`。
8. 结构化表路径用合成 `TableCandidate` 单测钉住；默认 mock 仍不发 TABLE_STRUCTURE。路线图 4.4 / 4.7 标明 specialist 推迟到 M7。
9. 四份 2026-09-03 proposed 架构 note 改为 rejected（已由后续落地 note 吸收），不再假装仍是提案。

## 考虑过的替代方案

- 保持 M4「已完成」并把跨页门禁留在 paper-anatomy Methods 段：具名夹具仍无法复现 4.1 跨页合同。
- 把 schema 全面升到 `0.2.0`：wire 形态未变，会迫使全部 fixture / golden / Literal 版本无意义地重写；改为记录例外并冻结后续升级纪律。
- 实现 letter-glue 拒绝空格分隔数字：PDFium 把 `\footnote` 抽成 `footnote 1`，会拆掉真实引用。
- 现在接入 GROBID / MinerU：重型依赖与不可复现环境仍不成立；确定性 baseline 保持。

## 后果

- M4 Exit Gate 在审查修复后关闭：跨页段落、Abstract、L2 嵌套、引用区间、Source Mapping 与 validator 跳变均有机械断言。
- 已知限制仍在 M4 落地 note：1 Layout → N Semantic、真实多列表格、GROBID 作者-年引用、图资源 PDF/SVG/raster、MathML 留给 M5/M7。
