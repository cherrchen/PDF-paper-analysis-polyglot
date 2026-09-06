# Agent Note: M4 第二轮审查正确性修复

Status: implemented

[中文](./2026-09-06-m4-correctness-repairs.md) | [English](./2026-09-06-m4-correctness-repairs.en.md)

## 问题

第二轮 Code Review（基于 `0346fe6`）确认 M4 模块齐全、基准测试能通过，但不足以支持「原始九个 Phase 全部完成」。具体缺陷是内容丢失、语义关联错误，以及测试只断言节点存在而不断言绑定到正确文本：

1. RenderComposer 把所有 `CAPTION_OF` 源节点跳过，TABLE 分支不回写 caption，表格标题从 Render IR 静默消失。
2. Dummy 翻译只改 `text`、原样复制 `marks`，固定前缀已使 CITATION / FOOTNOTE_REFERENCE / INLINE_EQUATION 指向错误字符。
3. 脚注按文本顺序接受首个同号数字，`Table 1` 会抢走真正的 `footnote1`；验证器零问题。
4. 脚注 label 整篇去重，后续页面同号或重复 `*` 无法关联。
5. 无编号 `HEADING_LIKE` 在 Abstract 之前被跳过，`Introduction` 被吞进 FRONT_MATTER 并标成 author。
6. SemanticValidator 章节递归无访问保护，环状树抛 `RecursionError`。
7. Viewer 只读 `fragments[0]`，跨页段落的后续源区域没有点击与高亮。
8. 语义节点 `provenanceIds` 恒为空，没有恢复操作、生产者版本或 evidence 链。

此前 [M4 Review 修复](2026-09-06-m4-review-repairs.md) 关闭的是第一轮 Exit Gate 缺口（跨页夹具、区间引用、弱测试）。那些修复仍然成立；本 note 补的是正确性与可追踪性，不重做引擎，也不把延期的 GROBID / 1 Layout→N Semantic / 真实多列表格改写成已完成。

## 决策

1. **表格标题：** 只有 FIGURE 消费绑定 caption；TABLE_CAPTION 作为独立段落输出。跨层断言标题文本与节点身份出现在 RenderDocument。
2. **翻译 marks：** 固定前缀平移偏移；其他改写用占位符保护 marked spans 并在译文中重建；占位符丢失则丢弃 marks，禁止复制失效源偏移。
3. **脚注：** 按 (page, label) 定位身份；候选按 letter-glue / PDFium 空格上标评分，排除 `Table 1` 一类结构编号；不确定或未关联时写 Issue。
4. **Front matter：** 作者行至少两个 name token；`Introduction` 等正文标题与机构行分开；无摘要、无编号章节时标题开启 SECTION。
5. **Validator：** 先检测环、父子一致性与重复归属，再做章节顺序；遍历带访问集合，坏树返回 `SECTION_STRUCTURE` ERROR。
6. **Viewer：** 遍历 SourceAnchor 的全部 fragment；`cross-page-paragraph` 的 mapping 与 `buildPairs` 回归覆盖每一页源区域。
7. **Provenance：** 每个节点与关系写入 `ProvenanceRecord`（producer / version / operation / inputRefs 含 layout region 与其 fusion 记录），文档带 `ProvenanceStore`。
8. **状态表述：** README 与路线图区分「基线已落地」与「原始九个 Phase 全部完成」。延期能力保留目标 milestone：1→N 与 MathML/图资源属 M5；GROBID 与真实多列表格属 M7。

## 考虑过的替代方案

- 把表格标题塞进 TABLE 段落块：M5 真表格排版前会把单元格与标题糊成一块；独立 TABLE_CAPTION 块保留身份与锚点。
- 真实翻译一律删除 marks：固定前缀可以安全平移，占位符能保住引用；全删会在进入 M5 前丢掉 CITATION。
- 要求上标 font 证据才关联脚注：PDFium 字号被合并 span 稀释，会拆掉现有 `footnote 1` 夹具。
- 现在把 M4 标回「未开始」：模块与 N→1 跨页合同仍然成立；需要的是正确性修复与诚实的延期标签。

## 后果

- 第二轮列出的内容丢失、错误关联、Viewer 截断与空 provenance 已修；测试改为断言文本跨度与跨层完整性，而不只是节点计数。
- M4 基线可用，但 1 Layout→N Semantic、GROBID 作者-年引用、真实多列表格、图 PDF/SVG/raster、MathML 仍按既有落地 note 延期。产品需求目录仍是占位，不能证明已对齐完整产品验收。
- 本 note 补充而非取代 [M4 Semantic Recovery Engine](../architecture/2026-09-06-m4-semantic-recovery-engine.md) 与 [第一轮 Review 修复](2026-09-06-m4-review-repairs.md)。
