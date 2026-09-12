# Agent Note: M7 Parser Ensemble & Quality System 落地

Status: implemented

[中文](./2026-09-12-m7-parser-ensemble.md) | [English](./2026-09-12-m7-parser-ensemble.en.md)

## 问题

M6 结束时，管线只硬编码一个 provider（`run_pipeline` 直接调用 `MockLayoutEvidenceProvider`），conflict resolution 只有 confidence 投票，没有探测、没有能力注册表、没有路由；confusion 的度量也不存在——benchmark 只做断言，不产出报告，任何 provider/算法升级都无法量化"变好还是变坏"（M7 Exit Gate 要求升级成为可量化的工程决策）。M4/M5 明细中标注「目标 M7」的延期项（1 Layout→N Semantic、真实多列表格结构、GROBID 书目 specialist、作者-年引用、STRUCTURE/METADATA specialist）同样悬置。

## 决策

1. **DocumentProbe（Phase 7.1，`pdf_pipeline/probe.py`）**：从 PhysicalDocument 单独推导 `native_text_ratio / scanned_page_ratio / math_density / table_density / image_density / estimated_columns / layout_complexity`（架构文档 §41 的字段集）。列数估计复用 `page_structure.detect_bands` 的逐页众数；表格信号复用 providers/table_grid 的启发式。全部为页面对象的确定性函数。`run_pipeline` 在物理层后立即探测，产出 ad-hoc 工件 `probe.json`（含探测值与 RoutingPlan），**不进 canonical schema**——与 viewer manifest 同类（诊断/路由工件）；schema 兼容冻结边界不受影响。
2. **Capability Registry（Phase 7.2，`pdf_pipeline/capabilities.py` + `data/capability-registry.toml`）**：capability → provider 序（primary/challenger/fallback），结构与架构文档 §35 一致，provider 名为 `pdfium / mock / docling-sim / grobid-sim / internal`。采用 **TOML + stdlib `tomllib`** 而非文档草图的 YAML：零新依赖、解析确定；若未来需要运行时可变配置再迁移（届时另记 note）。加载时强制不变量：`semantic.document`、`layout.reading_order`、`layout.column_detection` 必须内部所有。
3. **模拟 specialist provider（`pdf_pipeline/evidence/fake_specialists.py`）**：真实 MinerU/Docling/GROBID 依赖重（模型/Java），本轮按 roadmap Step 4 全部走确定性基线——`docling-sim` 产出 `TABLE_STRUCTURE` candidates（行/列/单元格网格），`grobid-sim` 产出 scholarly `METADATA`（title/author/abstract）与 `STRUCTURE`（section/REFERENCES/ABSTRACT 角色）candidates。真实 adapter 日后接同一 `EvidenceProvider` Protocol，机制无需改动。共享 `_CandidateSink` 公开为 `CandidateSink` 并支持按 provider 的 ID 前缀命名空间，多 bundle 并行不撞 ID。
4. **Adaptive Routing（Phase 7.3，`pdf_pipeline/routing.py`）**：`route_providers(probe, registry) -> RoutingPlan` 为纯函数——layout primary 始终运行；`table_density ≥ 0.1` 唤醒 docling-sim；`math_density ≥ 0.05` 给 layout primary 附加 formula capability；scholarly metadata/bibliography 常规运行（§42 标准论文路线）；无文本层的文档直接拒绝（与 FR-PDF-002 入口门禁一致）。`run_pipeline` 用 route 出的 bundle 列表喂 `recover_layout_document`（按 bundle 保留 provider 归属），并 merge 成单一 ensemble bundle 喂 semantic 恢复与 `evidence.json`（provider 字段记 `ensemble:<names>`，逐 provider 归属经 provenance `producer` 可追溯）。
5. **Conflict Resolution（Phase 7.4，`fusion.py`）**：标签投票从纯 confidence 改为 **confidence × authority 权重**（primary 1.5 / challenger 1.2 / fallback 1.0 / 未列出 0.8），capability 由 label 映射（TABLE→table.structure、FORMULA→formula.detection、其余→layout.region）。权重按**角色槽**计算，空 challenger/fallback 不得把 fallback 或未注册 provider 提升为 challenger。`fuse_page` 先汇总同一区域的候选再统一仲裁（含 TABLE/FORMULA）；禁止简单 majority vote（§43）。registry 缺省（None）时退化为旧行为。审查修复见 [M7 Review 修复](../bug-fix/2026-09-12-m7-review-repairs.md)。
6. **1 Layout→N Semantic（Phase 4.1 延期项，`sem_paragraphs.py`）**：`split_region_paragraphs` 按「行间隙 > 1.5×行高」与「内嵌编号标题行」把一个 region 的行拆成多个段落片段；**分段判定与标题分类都**复用 `heading_decision(numbered_only=True)`（带数学守卫，`2 dx = dy` 不拆段）。continuation group 中若某一区域发生 1→N 拆分，边界上的非标题片段仍用 `join_region_text` 续接，SourceAnchor 保留多个 region。内嵌标题不新开 SECTION（重挂树延后）。
7. **结构化表格链路（Phase 4.4 延期项）**：物理层 `_extract_text_spans` 在 PDFium rect 内部按「字符间隙 > 3×行高」二次拆分——表头列间隙 39–63pt、正文词/句间隙 ≤16.9pt，阈值只切表格单元格，正文 span 粒度与 PDFium rect 完全一致（基准/金零回归的前提）。共享 `table_grid.py` 负责网格检测：连续对齐多 span 行 + 列间距 ≥ 0.25×窄列宽（拒绝跨栏 gutter 伪网格）+ 行 run ≤ 12（拒绝多栏正文）。docling-sim 输出 TABLE_STRUCTURE，`sem_tables` 既有结构化路径直接消费。
8. **作者-年引用（Phase 4.7 延期项，`sem_bibliography.py`）**：`(Surname et al., YYYY)` / `(A & B, YYYY)` / 年份后缀（2020a）解析为 `surname:year` 键，与书目条目（剥掉 `[n]` 后首个大写词 + 年份）配对解析为 CITATION marks + CITES relations；未解析照常写 CITATION_RESOLUTION issue。新增 Tier-1 fixture `author-year-citations`（含 2020a 歧义后缀）。
9. **Scholarly metadata → front matter（Phase 4.2 缺口）**：`classify_front_matter` 新增 `metadata` 参数，grobid-sim 的 title/author 值可确认/补全 page-1 前缀块的 title/author 角色（启发式无 HEADING_LIKE 行时的兜底）。
10. **Confidence Calibration（Phase 7.5，`pdf_pipeline/calibration.py`）**：分桶报告机制（[0,0.5,0.6,0.7,0.8,0.9,1.0] 边界，桶内计数/正确率 + 单调性诊断）。**数值校准只作诊断、不作门禁**：`compare()` 把校准准确率变化写成 `diagnostic` 行，永不标 `REGRESSED`。现有 hand truth 是片段级（readingOrder 只列关键区域），未命中片段的 region 无法判负例——区域级标注真值是数值校准的前置（同 M3 "Region Precision 待区域级标注" 的立场）。
11. **Quality Metrics（Phase 7.6，`metrics.py::quality_report`）**：聚合 physical text coverage、region recall/precision、pairwise/sequence ordering、`semanticExpectationCoverage`（kinds / minCounts 期望满足度）、table-structure coverage、citation resolution rate、source/render mapping coverage、issue 的 category 与 severity 计数。`paragraphRecoveryAccuracy` / `sectionHierarchyAccuracy` 在无区域级真值时恒为 null，绝不把 ERROR 有无或节点种类检查伪装成准确率。
12. **Regression Benchmark（Phase 7.7，`tests/benchmark/run_benchmark.py`）**：对全部已编译 fixture 跑 routed ensemble → 产出报告 → 与 `tests/benchmark/baseline.json` 对比（higher-is-better、epsilon=1e-3）。回归即非零退出的条件：可测指标下降、基线 fixture 缺失、原可测指标变为 null、ERROR/FATAL 计数增加。WARNING/INFO 只记录不阻断。`just benchmark` / `benchmark-report` / `benchmark-update-baseline`；nightly 工作流在 `just latex-smoke` 后运行门禁。baseline 更新遵循 golden 政策（须在提交信息中给理由）。

## 考虑过的替代方案

- **物理层 char 级重聚类**（首个实现）：以 loose charbox 全量替换 PDFium rect。会抬高 span 高度分布 → body_font 漂移 → 阻断/标签启发式连锁偏移（公式编号丢失、分栏结构漂移），已回退。窄方案（仅 rect 内 > 3×行高间隙二次拆分）在 benchmark/golden 零回归下达到同一表格目标。
- **YAML registry + pyyaml 依赖**：TOML（stdlib tomllib）零依赖且同表达力；文档 §35 的 YAML 草图只是形式。
- **table_region_candidates（数字行启发式）直接产出结构**：它依赖"整行单 span"前提，单元格拆分后失效；改为共享网格检测（mock 出 REGION 候选、docling-sim 出结构）。
- **本轮接真实 MinerU/Docling/GROBID**：重依赖、需模型/Java 服务；simulated provider 已验证 ensemble 机制，真实 adapter 按同一 Protocol 接入（providers.py docstring 承诺）。
- **校准数值进门禁**：真值粒度不足（见决策 10），绝对精度无意义；校准变化只记 diagnostic，门禁看 fixture/指标/ERROR。

## 后果

- `run_pipeline` 产物新增 `probe.json`（ad-hoc，非 canonical）；`evidence.json` 的 `provider` 字段变为 `ensemble:<names>`，`rerender_workspace` 不读 evidence，重渲染路径不受影响。
- 布局恢复对同一 PDF 的输出与 M6 相比**有变化**（表格行 span 拆分 + authority 权重 + ensemble 候选）；layout/semantic benchmark、golden 全部零回归通过后落地，baseline 固化为 M7 基线。
- 表头行（未拆分的整行 rect）目前不在 TABLE_STRUCTURE 单元格内（行间隙小于阈值），其文本保留为独立 TEXT region——内容不丢失（质量优先级 1），表头并入单元格待 specialist 真源。
- `dataset` 范围：`table_grid_regions` 对多栏正文页有行数上限与列间距比例双重防误判；若真实语料出现新误判形态，调 `TABLE_MAX_GRID_ROWS`/`COLUMN_GAP_RATIO` 并走 benchmark 报告。
- 验证：见 [M7 Review 修复](../bug-fix/2026-09-12-m7-review-repairs.md)；e2e 不受影响（viewer 数据契约未动）。
- 文档：`docs/development/roadmap.md` M7 明细与本 note 为当时基线。进入 M8 前的 PRD 三项收口见 [PRD 过滤 roadmap 延期项](../process/2026-09-12-prd-filters-roadmap-deferrals.md)、[可选真实 parser 依赖](./2026-09-12-optional-parser-adapters.md)、[区域级标注真值](./2026-09-12-region-level-layout-truth.md)、[Figure PDF fragment](./2026-09-12-figure-pdf-fragment.md)。
