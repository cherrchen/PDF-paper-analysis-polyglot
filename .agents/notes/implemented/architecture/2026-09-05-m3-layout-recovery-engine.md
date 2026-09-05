# Agent Note: M3 Layout Recovery Engine 落地

Status: implemented

[中文](./2026-09-05-m3-layout-recovery-engine.md) | [English](./2026-09-05-m3-layout-recovery-engine.en.md)

## 问题

M2 Walking Skeleton 的版面恢复是刻意极简的：每页一个 band、朴素中缝分栏、每行一个 region、sort(y, x) 线性阅读流、caption 启发式在语义层内做几何猜测，且完全没有第三方 parser evidence 的接入点。M3 要求把版面恢复从「能恢复」提升为「可靠恢复页面结构」，并打通 Evidence 契约（`schemas/evidence/schema.json`）的第一条真实消费链。

## 决策

八个 Phase 全部完成（Roadmap M3，Phase 3.1–3.8），模块划分与关键决策如下。全部实现位于 `packages/python/pdf-pipeline/src/pdf_pipeline/`，均为确定性算法（同输入字节产出逐字节相同的 LayoutDocument），无 LLM / 无优化器（Roadmap §4 Step 4）。

1. **Evidence 适配器边界（3.1）**：新增 `pdf_pipeline.evidence` 子包。`EvidenceProvider` Protocol 是 parser 输出的唯一入口；`MockLayoutEvidenceProvider` 是确定性基线 provider，模拟 MinerU 类版面专家，覆盖 REGION/TABLE/FORMULA/HEADER/FOOTER 候选（含 per-candidate ProvenanceRecord）。`normalize.py` 负责 label normalization（provider 原生 label → `LayoutLabel`，映射幂等）、coordinate normalization（provider 空间 → canonical page space，v0.1 收窄为 bounding rect）与跨 provider 候选 matching key。**不安装真实 MinerU**：重型原生依赖需 Agent Note 且环境不可控，真实适配器后续以同一 Protocol 接入（mock 与真实 provider 在 fusion 侧完全同权）。
2. **Region Fusion（3.2）**：`pdf_pipeline.fusion`。候选匹配要求几何一致（IoU ≥ 0.4 或 containment ≥ 0.7）且 label 兼容（`_LABEL_SIMILARITY` 矩阵），text preview 重叠加分；label 按 confidence 加权投票，一致性加分，上限 0.95（版面恢复永不确定）。TABLE/FORMULA 结构化候选几何匹配（跳过 label 相似度）并吸收覆盖的文本块（表格行）；cell noise（被吸收区域内的段落候选）丢弃；未匹配候选成为 evidence-only region（保 recall）。所有融合输出携带 reason（可观测）。
3. **Band/Column（3.3+3.4）**：`pdf_pipeline.page_structure` 用递归 XY-cut：先横切（贯穿全幅的 y-gap ≥ 9pt），再竖切（贯穿条带全高的 x-gap ≥ 7pt）。**结构检测先于文本分块**——否则通栏行（标题/摘要）会把左右两栏桥接进同一个块。单行内部的 x-gap（公式编号、表格单元格）不贯穿条带高度，永不误切；宽度 < 15% 页宽的 x 岛（公式编号）并入最近邻；图形（image + vector path）在列检测前先聚成簇（TikZ 箭头以不利访问顺序桥接相邻块，需收敛合并到不动点）。非平衡栏（左栏先结束）由 gutter 切分自然保持正确阅读顺序。SPANNING/FULL_WIDTH 分类需要文档级上下文：跨页二次分类（`reclassify_bands`），独占一页的宽图按文档栏式判定。
4. **ReadingFlowGraph（3.5）**：`pdf_pipeline.reading_flow`。阅读顺序完全由 band/column 结构驱动：band 自上而下、列自左而右、列内自上而下，**无任何 sort(y, x)**。每条 ReadingEdge 带 reason + confidence：SAME_COLUMN/NEXT_COLUMN、BEFORE/AFTER_SPANNING_BLOCK（横跨 band 转换）、CAPTION_ASSOCIATION（layout 关联对的方向覆盖）。
5. **Paragraph Continuation（3.6）**：相邻文本 region 间：源文本无终止标点（剥离右引号/括号后）是强信号（+0.45），目标小写开头（+0.25）与源末行满宽（+0.15，断行发生在栏/页/图边界）辅助，≥0.6 判 CONTINUATION 并覆盖位置 reason；被 figure/table/formula 打断的文本对额外加一条跨打断的 CONTINUATION 边。M4 语义恢复据此合并段落。
6. **Caption Association（3.7）**：`pdf_pipeline.captions`。layout 层依据 caption 前缀（`Figure N`/`Table N`）、垂直距离（≤60pt，图下/表上优先）、水平对齐、字号、宽度比打分，贪心 1:1 分配，输出 `LayoutGroup(FIGURE_BLOCK/TABLE_BLOCK)`。`semantic.py` 改为消费该 group（caption 前缀类型与目标 kind 冲突时拒绝配对），不再自带几何启发式。caption 可以比居中的图更宽（LaTeX 惯例），硬上限放宽到 2.5×。
7. **Footnote Recovery（3.8）**：`pdf_pipeline.footnotes`。页底 zone（≥72% 页高）+ 小字号（≤0.95×正文）+ 标记前缀（数字/符号）识别 FOOTNOTE region；标记下方的未标记小块并入同一 flow。footnote 有自己的 FOOTNOTE_FLOW 链，与 header/footer 一并**不进入 primaryFlow**（schema 描述即如此声明）。
8. **物理层扩展**：`physical.py` 新增 vector path 对象提取（`FPDF_PAGEOBJ_PATH`，M2 刻意留白）。`\rule`、TikZ、booktabs 规则线进入 PhysicalDocument；figure 聚类过滤厚度 <2pt 的装饰线（规则线），避免伪 FIGURE。这是 M3 版面检测的必要输入，属于 Physical 层「客观内容」职责的自然补全。
9. **下游适配**：`semantic.py` 为 FOOTNOTE region 生成 FOOTNOTE 节点（附加在文档尾部，不进主流程），每个节点在 `attributes.layoutRegionId` 记录来源 region，`pipeline.build_source_anchors` 改为**基于身份**配对 anchor（不再按位置枚举配对）；`render_composer.py` 把 FOOTNOTE 渲染为段落块（内容完整性优先级高于版面保真，Roadmap §8）。管线新增 `evidence.json` 输出（第 7 份 canonical 文档）。
10. **Benchmark（§6）**：`tests/fixtures/layout-truth/<fixture>.json` 为 11 个 Tier-1 fixture 的手工 ground truth（阅读顺序 = LaTeX 源视觉顺序的文本片段、caption 配对、footnote 数量、band/栏不变量），`tests/benchmark/test_layout_benchmark.py` + `pdf_pipeline.metrics`（token 前缀匹配）计算 Region Recall、pairwise ordering accuracy、sequence accuracy。门槛：recall ≥ 0.9、pairwise ≥ 0.95、sequence 全对、caption/footnote 断言全过。**当前全部通过**。双栏稳定性用外部真实论文验证（BERT 页 1 = FULL_WIDTH 标题/摘要 + 2 栏正文；Attention 单栏页无 MULTI_COLUMN）。

## 考虑过的替代方案

- 安装真实 MinerU：数 GB 模型下载 + 原生依赖，违反「重型依赖需 Agent Note」约束且不可复现环境；mock provider 与真实 adapter 同一 Protocol，接入成本仅为一个类。
- 全页投影直方图分栏：单行内部 gap（公式编号）与真 gutter 无法区分，产生 16 列 band；XY-cut 的「gap 贯穿全幅/全高」约束从几何上排除了单行噪声。
- 保留 M2 位置配对 anchor（第 i 个节点 ↔ 第 i 个 region）：footnote 节点加入后错位；`attributes.layoutRegionId` 是身份模型（[source-mapping identity note](../../proposed/architecture/2026-09-03-source-mapping-identity-model.md)）的正确形态。
- Golden SemanticDocument 保持不变：smoke 的段落块合并与 HEADING 误判修正属于预期行为变化，按 `docs/testing/golden.md` 流程人工审查 diff 后更新。

## 后果

- M3 Exit Gate 达成：Band/Column 检测稳定（Tier-1 不变量断言 + 真实论文双栏）、Reading Order 达标（pairwise/sequence 全绿）、Caption Association 达标、跨页/跨栏 continuation 可用（cross-page-paragraph fixture 断言）、LayoutDocument 全部通过 schema 校验与层分离检查、无严重结构错误。
- `pdf-pipeline` 新增模块：`geometry`、`furniture`、`evidence/`、`fusion`、`page_structure`、`blocks`、`captions`、`footnotes`、`reading_flow`、`metrics`；`layout.py` 变为编排器。测试 183 个（新增 6 个测试文件 + benchmark），`just check` 全绿。
- 已知限制（有意保留）：(1) 表格 cell 结构依赖 PDFium 合并行为，行内 cell 已合并时只能恢复为整块 TABLE region，真实 TABLE_STRUCTURE 需 MinerU；(2) 数学片段以行级 TEXT region 混入阅读流（M4 以 FORMULA evidence 与语义恢复处理）；(3) Region Precision 的 ground truth 目前只有文本片段级（无完整区域级人工标注），指标以 recall + 顺序为主；(4) `attributes.layoutRegionId` 是 open attribute bag 的身份引用，不含几何。
- 无新增第三方依赖。
