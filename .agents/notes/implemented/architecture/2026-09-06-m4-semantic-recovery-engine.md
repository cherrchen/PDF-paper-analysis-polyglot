# Agent Note: M4 Semantic Recovery Engine 落地

Status: implemented

[中文](./2026-09-06-m4-semantic-recovery-engine.md) | [English](./2026-09-06-m4-semantic-recovery-engine.en.md)

## 问题

M3 之后版面层已可靠（band/column/reading flow/caption/footnote region），但 `semantic.py` 仍是 M2 极简化：只走 `primaryFlow` 逐 region 建扁平节点（HEADING level 恒 1），完全未消费 M3 交接的 evidence——CONTINUATION 边、TABLE/FORMULA region 文本、evidence 层的 TABLE_STRUCTURE / FORMULA / STRUCTURE / METADATA 候选（`normalize.py` 明确留给 M4）。Roadmap M4（Phase 4.1–4.9）要求把视觉结构恢复为论文结构：段落合并、章节层级、表格/公式/脚注/书目语义、完整 Source Mapping、SemanticValidator。

## 决策

九个 Phase 全部完成，引擎重写为 `_Recovery` 单遍恢复 + 七个 `sem_*` 阶段模块（全部位于 `packages/python/pdf-pipeline/src/pdf_pipeline/`，确定性、无新增第三方依赖——延续 M3「不装 MinerU/GROBID」决策，真实 provider 走同一 evidence 消费路径）：

1. **契约（先行 additive patch）**：`InlineMarkType` 新增 `FOOTNOTE_REFERENCE`（Roadmap 4.6 点名 FootnoteReference；复用 SUPERSCRIPT 会丢失 target 语义）。schema + fixture + `just generate` 双语言绑定 + 跨语言 roundtrip 一次原子变更，版本仍 0.1.0（冻结前政策允许）。
2. **输入管道（Phase 4.1 前置）**：`pipeline.region_lines_from` 把 region 背后的 physical span 逐行（文本+rect+字号）喂给语义层；`region_texts_from` 的 kind 过滤扩为 TEXT/FOOTNOTE/TABLE/FORMULA。`recover_semantic_document(layout, texts, *, lines=None, evidence=None)` 两参数可选，缺省时启发式优雅降级（golden 测试不传 evidence 仍确定性）。
3. **段落合并（4.1）**：`sem_paragraphs`。primaryFlow 上相邻且被 CONTINUATION 边相连的**正文** region 并成一个 PARAGRAPH 节点；`attributes.layoutRegionIds`（复数 list，阅读序）取代 M3 单数 `layoutRegionId`；连接去 `\x02` 软断字符、行尾连字符接词。合并 confidence = min(0.75, 链上最小 CONTINUATION confidence)，reason `paragraph merge: N regions`。`pipeline.build_source_anchors` 原生支持 N regions → 1 anchor → 1 node（`SourceAnchor.fragments` 多元素，契约自 M1 即如此设计）。headings/captions/front matter/equation 成员不参与合并（label 噪声大于 pattern 精度）。
4. **章节树（4.2）**：`sem_sections` + 引擎 `_open_section` 栈。heading level 来自编号 pattern（`1.2.3` → level 3），不信任字号；无编号 `HEADING_LIKE` 需过 prose 形状闸（含 4+ 字母英文词、无 `=^_\()`），杜绝数学碎片与年份成为标题。SECTION 容器（`attributes={level,numbering,title}`）嵌套 HEADING+后续内容直到 level ≤ 自身；DOCUMENT root 首子为 FRONT_MATTER。front matter = page-1 开头到第一个结构标题/正文句/摘要体前：最大字号 HEADING_LIKE = title、`Abstract` 行切出 abstract-title/abstract、ISO 日期 = date、其余短大写行 = author。`References` 等 unnumbered 标题保持 level 1。
5. **Figure / Table / Equation（4.3–4.5）**：FIGURE 节点带 `FigureContent.label`（从绑定 caption 前缀解析）；TABLE 优先消费 `TableCandidate` 结构化 evidence（`sem_tables`），PDFium 合并行为下退化到行 fallback（每 physical line 一行一列），内容永不丢失、reason 可观测。公式分三路：FORMULA region 或 CONTINUATION 链上短数学碎片 run（`sem_equations.display_groups`，`_strong_math` 双保险防误判）→ EQUATION 节点；`(n)` 编号 region 吞并为 `EquationContent.number`（前挂/后挂都支持，align 断链的指数尾巴吸收）；行内 `f(x)=x^2` 用算符锚定窗口扩展打 `INLINE_EQUATION` mark（PDFium 宽空格排版，`MULTI_COL UMN` 类扁平化标识符不命中）。inline math 所在段落永不成 EQUATION 节点（prose 词 4+ 字母一票否决 display 判定）。
6. **Footnote（4.6）**：`sem_footnotes`。footnote 体前导 marker 数字 ↔ 正文中「字母后紧跟的数字」（`efficiency1` 形态；数字串与页码/年份被已知 marker 集合 + 词形约束排除），产出 `FOOTNOTE_OF`（footnote → 宿主 paragraph，方向与 M1 fixture 一致）+ `FOOTNOTE_REFERENCE` mark（带 targetNodeId + label）。同页校验：跨页同号不误连。
7. **Bibliography / Citation（4.7）**：`sem_bibliography`。`References` 标题 → BIBLIOGRAPHY 容器；`[n]` 前缀段落 → BIBLIOGRAPHY_ENTRY（label 属性），CONTINUATION 碎片并入前条目（正是 4.1 合并语义的复用）；正文 `[n]`/`[n,m]`/`[n–m]` → 每个数字一条 CITATION mark + CITES relation，未解析编号保留文本 + `CITATION_RESOLUTION` WARNING issue。
8. **SemanticValidator（4.9）**：新模块 `sem_validate.validate_semantic_recovery(semantic, layout, texts) -> Issue[]`：孤儿节点 / 树不可达（ERROR SECTION_STRUCTURE）、heading level 跳变（WARNING）、无 CAPTION_OF 的 caption（WARNING FIGURE_RECOVERY）、内容 kind 缺 `layoutRegionIds` 或引用未知 region（ERROR SOURCE_MAPPING）、mark/relation target 类型错（WARNING CITATION_RESOLUTION）、primary-flow 内容 region 覆盖检查（漏绑 WARNING/ERROR 按覆盖率 <0.95 升级，重复绑定 ERROR）。`run_pipeline` 在恢复后运行 validator 并把结果合入 `semantic.issues`；恢复期 issue（重复条目、未解析引用、空表）由引擎自带。单元测试对每种破坏逐一验证检测生效（`test_semantic_validate.py`）。
9. **id 稳定性**：所有节点 id 改为 `stable_uuid(layout.id, "node", <语义盐>)`（region id / "root" / "front-matter"），废除位置计数——增删任何节点不再扰动其余 id；SECTION/BIBLIOGRAPHY 容器用独立盐前缀。golden canonicalizer 对 `layoutRegionIds` 列表逐元素 remap，`\maketitle` author 特判（M3 遗留）删除——author 现在确定进入 FRONT_MATTER。
10. **渲染兜底**（非 M5 范围，防静默丢内容）：RenderComposer 把 TABLE 投影为行优先 `cell | cell` 段落、EQUATION 为 `unicodeText|rawText (number)` 段落、BIBLIOGRAPHY_ENTRY 直接可译（`paper_llm.TEXT_NODE_KINDS` 扩）。容器 kind 无文本自然不产 block。
11. **Exit Gate 夹具与 benchmark**：新 Tier-1 夹具 `paper-anatomy`（title/author/date/abstract/两级 section/figure+caption/table/编号 equation/footnote/thebibliography+正文引用，双页；禁 `\int` 延续 c1a3f75 的 PDFium 移植性教训）+ metadata YAML；12 个 `layout-truth/*.json` 全部新增 `semantic` 期望块（kinds/minCounts/captionOf/footnotesLinked/citationsResolved/marks/equationNumbers/headingLevels/mergedParagraphNodes/multiFragmentAnchors/tableCellsMin/coverageMin/noErrors）；`tests/benchmark/test_semantic_benchmark.py` 机械断言整个 M4 Exit Gate（含 bundle 引用完整性与多 fragment anchor 数）。

## 考虑过的替代方案

- **零 schema 变更（SUPERSCRIPT 复用）**：可行但 `FOOTNOTE_REFERENCE` 是 Roadmap 4.6 点名契约，viewer/分析层需要类型区分；0.1.0 冻结前 additive enum 政策明确允许。
- **公式碎片在 evidence 层调参产生 FORMULA region**：尝试过（`_looks_like_formula` 阈值 0.25→0.15 保留为改进，但 Tier-1 数学碎片仍多为 TEXT）；语义侧 CONTINUATION 链 + 数学密度 + `_strong_math` 双信号是决定性路径，evidence 侧只做增益。
- **GROBID/Meta 风格 STRUCTURE+METADATA evidence 驱动 front matter/section**：mock provider 不产这些候选（normalize 跳过 STRUCTURE/METADATA 不变）；几何+文本 pattern 在 Tier-1 上已确定性达标，真实 GROBID 适配器将来走同一注入路径（`evidence=` 参数已预留 TABLE/FORMULA 消费）。
- **段落合并用并查集全局闭包**：会在跨 FIGURE 打断链上误合并被 M3 跨打断边连接的远端块；改为「flow 相邻 + 边存在」线性链，顺序保真。
- **footnote marker 用字号上标检测**：PDFium 的 FontRef.name 恒空、字号被合并 span 稀释，不可靠；文本形态（字母+尾数字 + marker 集合）在 12 夹具上零误报。
- **golden 直接保留旧树**：FRONT_MATTER/EQUATION/layoutRegionIds 是预期合同演进，按 `docs/testing/golden.md` 人工审查 diff 后重新 bless（本 note 即审查记录）。

## 后果

- M4 Exit Gate 达成（paper-anatomy 单篇恢复全部十类结构 + `just test-python` 中 semantic benchmark 全绿；全 12 夹具 `validate_semantic_recovery` 零 issue、bundle 引用零断裂、层分离零违例）。
- `pdf-pipeline` 新增模块：`sem_paragraphs`、`sem_sections`、`sem_tables`、`sem_equations`、`sem_footnotes`、`sem_bibliography`、`sem_validate`；`semantic.py` 成为编排器。
- 契约变化（additive，0.1.0 内）：`InlineMarkType` 增 `FOOTNOTE_REFERENCE`；semantic 节点 `attributes.layoutRegionIds: list[str]` 取代 `layoutRegionId: str`（open bag，非 schema 字段；viewer 未消费该键，无破坏）。
- 已知限制（有意保留）：(1) 表格行 fallback 在 PDFium 合并单元格文本时只有一列，真实多列结构需 TABLE_STRUCTURE evidence（MinerU 类 provider 接入即得）；(2) `2 Methods`-style 之外的特殊标题命名（Appendix、Related Work 等）不识别 level，需要编号或 HEADING_LIKE+prose 形状；(3) citation 解析只认数字括号模式，author-year 文本引用不产 CITES（Roadmap 4.7 的 GROBID 路径未接）；(4) INLINE_EQUATION 对 `x_1` 这类无空格排版可靠、对 PDFium 把标识符拆断的 `MULTI_COL UMN` 已用「裸 `_` 需后跟数字」规则排除，理论上仍可能漏掉罕见的 `_` 数学（不丢内容，只是不打 mark）；(5) `numbering` 只从文本 pattern 来，不做版面层级推断。
- 无新增第三方依赖；`just generate` 重跑了双语言绑定且 `git diff` 干净。
