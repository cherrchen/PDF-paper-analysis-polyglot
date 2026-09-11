# Agent Note: M6 Bidirectional Reader 落地

Status: implemented

[中文](./2026-09-11-m6-bidirectional-reader.md) | [English](./2026-09-11-m6-bidirectional-reader.en.md)

## 问题

M5 后 Viewer（`apps/web`，M2 骨架）仍是点击跳转的对照桌：target 每节点只保留 `fragments[0]`，跳转只换页不定位，无空间索引、无 Inspector、无同步滚动、无翻译交互。Exit Gate 要求定位原文↔译文完全不依赖 `source page ≈ target page`（PRD FR-SYNC-004 禁止页码/坐标猜测），而 viewer 数据面（v1）没有发射 Inspector 所需的文本、置信度、relations、provenance、翻译与术语。

## 决策

1. **Viewer 数据契约 v2**（`_write_viewer_assets` 唯一生产者）：canonical MappingBundle 字段照旧展开，新增 `semanticNodes`（全量 content/confidence/parentId/provenanceIds）、`semanticRelations`、`translation`、`provenance`、`issues`；`viewer-meta.json` 用逐页尺寸数组替换单页字段；`run_pipeline` 在 workspace 落一份 `source.pdf`；mapping/meta 原子写（tmp + replace），防 vite 读到半截文件。
2. **前端网格空间索引**（`apps/web/src/spatial.ts`）：按页 8×12 均匀网格，cell 尺寸取该页 meta，缺页回退同侧已知尺寸；`hitTest`（面积升序）与 `inBand`（y 升序）先取候选再精确 rect 测试。
3. **多 fragment + 确定性跳转**：`Pair` 双侧收集全部 fragments；`pickCounterpart` 在对侧「≥ origin 页码」的最小页上取最近 y，无则取第 0 个；`activate` 渲染 destination 页、按 rect 比例滚动居中、focus overlay 按钮；同步滚动用 ±12 pt 中线条带查询，查不到就不动对侧；程序性滚动 250 ms 抑制防回环。
4. **Semantic Inspector**（`apps/web/src/inspector.ts`）：稳定 id 的锚点/原文/译文/relations/confidence/provenance/issues/术语/citations 面板；`nodePlainText` 四类 content 判别与 canonical oneOf 分支一一对应；越界 mark 显示 `mark out of range` 不抛错。
5. **局部重渲染**（FR-TRANS-004）：`rerender_workspace(workspace_dir, *, viewer_data_dir, node_ids)` 载入 workspace 六份 canonical 文档（`load_document`，kind 以 `_ROOT_MODELS` 为准），校验 `node_ids ⊆ translation.entries` 键集，retranslate → compose → 投影/编译 → 恢复 RenderAnchor → 复用旧 source 侧绑定重建 MappingBundle → 重写 workspace + viewer 包。零源 PDF 重解析；provider/cache 构建与 `run_pipeline` 共用 `_build_translation_provider`。
6. **stdlib reader API**（`apps/api`）：`GET /api/health` + `POST /api/retranslate`（400/409/413/405/500 契约），`ThreadingHTTPServer` + 模块级 `threading.Lock` 串行化；业务放 `paper_api/retranslate.py`，`__main__` 薄接线；重依赖懒导入保持 <1 s 启动。
7. **viewer 夹具切到 `paper-anatomy`**（2 页、全元素、真实跨页 RenderAnchor）；`just serve-reader` 与 Playwright webServer 用同一 `sh -c`（api :8000 + vite dev :4173），`/api` 经 vite proxy 同路。

## 考虑过的替代方案

- **Python 预构建空间索引 / 真 R-tree**：索引语义是前端交互（hit-test/条带），数据量论文尺度（<10³ rect），网格 O(1) 且零依赖；预构建只会把前端行为绑死到生成期。接口 `PageSpatialIndex` 不变即可日后换 R-tree。
- **canonical mapping schema 升 0.2.0 加 `renderAnchors` 容器**：牵动生成绑定、fixtures、跨语言 roundtrip；validators 注释与 M2 note 已确立「render anchor 几何外部化」。几何继续留在 viewer 包；待 M7/M8 服务端需要消费几何时再议 schema note。
- **FastAPI**：仓库有意零 web 框架；stdlib 已够（两路由 + JSON）。
- **单节点 LaTeX 重编译**：无法在输出流中定位单节点边界；整文档 target 重编译把代价集中一次（dummy 夹具 ~1.4 s）。
- **沿用 figure-caption 作 viewer 夹具**：单页无跨页/多 fragment，6.4 与 Exit Gate 不可证。

## 后果

- `apps/web/src/mapping.ts` 抛错 `unsupported viewer data version: <n>`（仅 2 合法）；v1 包不再被任何代码接受（clean cutover，无兼容分支）。
- `pickCounterpart` 的「最小合格页」规则是有意的确定性：origin 在末页时可能回跳对侧第 0 页；这是「同一页或对侧下一页优先」约束的确定化，不是 bug。
- `retranslate` 后 target 的 pdf.js document 必须重建（版面已变）；旧页面几何失效会导致错误滚动。dummy provider 下输出逐字节确定，e2e 因此只锁协议与回稳，不断言文本变化（真 provider 路径由 M5 结构测试与手工验证承诺）。
- viewer 包新增字段只扩展 viewer 发射逻辑，canonical schema 零变更；若未来发现 Inspector 需要 canonical 缺失字段，另开 schema note，不在 M6 内升版。
- 验证：`just test-python`、`pnpm exec vitest run`（37）、`just test-integration`、`just test-e2e`（12，含多 fragment 高亮、同步滚动、Inspector、浏览器内真实重译）全绿。`tests/benchmark/test_semantic_benchmark.py` 新增 `anchorCoverage ≥ 0.8` 度量。
- 文档：[`docs/architecture/reader.md`](../../../../docs/architecture/reader.md)（[English](../../../../docs/architecture/reader.en.md)）为当前态真源。
- 后续正确性修复见 [M6 Review 修复](../bug-fix/2026-09-11-m6-review-repairs.md)。
