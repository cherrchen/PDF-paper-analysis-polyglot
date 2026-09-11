# 阅读器（M6 Bidirectional Reader）

[中文](./reader.md) | [English](./reader.en.md)

双向跳转架构见 [`document-architecture.md`](document-architecture.md) 第 32–33 节。本页描述当前态实现：viewer 数据契约 v2、前端空间索引、导航/滚动/高亮/focus 行为、Semantic Inspector、reader API 与局部重渲染。

## Viewer 数据契约 v2

`pdf_pipeline.pipeline._write_viewer_assets` 是 `viewerDataVersion: 2` 包的唯一生产者。每次发布写入完整 `revisions/<id>/`（`mapping.json`、`viewer-meta.json`、`source.pdf`、`target.pdf`），再原子替换 `manifest.json` 指向该 revision；稳定别名 `/data/mapping.json` 等在 manifest 之后更新，供夹具与直接拉取使用。阅读器始终先读 manifest，优先按 revision URL 加载；Vite 对启动后新建的 `revisions/` 可能回退成 `index.html`，此时改拉带同一 revision cache-buster 的稳定别名。dev/preview 通过 `serve-public-data` 插件按请求从 `public/data` 读盘，避免把 `/data/*` 交给 SPA fallback。canonical MappingBundle 字段照常展开（schema 保持 `mapping` 0.1.0，零变更），并附 viewer 私有投影：

| 键 | 内容 |
| --- | --- |
| `semanticNodes` | 全节点（跳过根）：`id/kind/parentId/content/confidence/provenanceIds`，content 与 confidence 为 canonical dump |
| `semanticRelations` | `semantic.relations` 全量 |
| `sourceRegions` | `{id, pageIndex, geometry}`（不变） |
| `renderAnchors` | RenderAnchor dump（几何留在 viewer 包，不进 canonical mapping，见 [M2 note](../../.agents/notes/implemented/architecture/2026-09-04-m2-walking-skeleton.md)） |
| `translation` | `{targetLocale, sourceLocale?, providerModel?, terminologyRevision?, terminology?, entries[{semanticNodeId, content, confidence?, providerModel?, cacheKey?}]}` |
| `provenance` | `semantic.provenance.records` |
| `issues` | semantic + mapping + translation 的 IssueStore.issues 拼接 |

`viewer-meta.json` 携带逐页尺寸数组 `sourcePages` / `targetPages`（`{widthPt, heightPt}[]`）：同步滚动与被查页几何必须用真实页尺寸，不允许套用第 0 页。

`run_pipeline` 把输入字节复制到 workspace 的 `source.pdf`，`rerender_workspace` 由此免用户重传源 PDF。

## 空间索引（6.1/6.2）

`apps/web/src/spatial.ts::PageSpatialIndex` 是前端侧按页均匀网格（8 列 × 12 行，cell 尺寸取该页 meta 尺寸，缺页回退同侧第 0 页已知尺寸）：

- fragment 注册进 rect 覆盖的所有 cell；点查询与条带查询先取 cell 候选去重，再精确 rect 测试。
- `hitTest(page, x, y)`：包含点的 fragment，面积升序。`inBand(page, yMin, yMax)`：与水平条带相交者，rect.y 升序。零面积 rect 与未知页不抛错，返回空。
- 论文尺度 fragment < 10³，cell 查找 O(1)；密集重叠时仍扫描该 cell 的候选。接口不变的前提下可替换真 R-tree（见 [M6 note](../../.agents/notes/implemented/feature/2026-09-11-m6-bidirectional-reader.md)）。

## 导航行为（6.3/6.4）

`apps/web/src/mapping.ts` 的 `Pair = { sources: Fragment[]; targets: Fragment[] }` 收集双侧全部 fragments（多 fragment 是一等公民）。节点身份来自绑定。`pickCounterpart(pair, origin, originRect)` 是字符级 mapping 缺席时的**节点内落点启发式**：在对侧「不小于 origin 页码」的最小页上取 y 最近者；不存在则取对侧第 0 个。它不承担 FR-SYNC-004 的身份判定。点击选择走空间索引 `hitTest`（最小面积优先）；键盘激活仍使用获焦按钮对应的 fragment。

`apps/web/src/reader.ts` 的 `DualPaneReader.activate(nodeId, origin, fragment)`：

1. destination pane 渲染 `pickCounterpart` 所在页（每侧 `PaneRenderer` 取消旧 PDF.js 任务，只提交最新 generation；同页只重画 overlay）；
2. 按 `fragment.y / pageHeight × canvasHeight` 把该 fragment 滚到 pane 视口中线（clamp）；
3. 对 destination 的 overlay 按钮 `focus({preventScroll:true})`；
4. origin 侧重绘保留 `aria-pressed` 选中态；active 态跨翻页保留。选中态经 `setActiveNode` 统一更新 overlay 与 Inspector。

同步滚动（`#sync-scroll`，默认关）：滚动侧视口中线 ±12 pt 条带 `inBand` 查询 → 首个含 paired 节点的命中 → `pickCounterpart` → 对侧渲染并滚动到位。查不到节点时什么都不做（禁止页码猜测回退）。程序性滚动后 250 ms 内忽略对侧 scroll 事件防回环。

## Semantic Inspector（6.5）

`apps/web/src/inspector.ts::renderInspector(root, model, nodeId, opts)`。面板含稳定 id（e2e 选择器）：`#inspector-node-id`（完整 SemanticNodeID）、`#inspector-kind`、`#inspector-anchors`（`source p{n} [x,y w×h]` 双侧逐条）、`#inspector-source-text`、`#inspector-translation`（无 entry 显示 `Not translatable`，BIBLIOGRAPHY_ENTRY 按 PRD FR-CITE-004 不进翻译层）、`#inspector-relations`（双向 relation 按钮可跳转）、`#inspector-confidence`（节点 score + reason + target anchor 置信）、`#inspector-provenance`、`#inspector-issues`（有则显示）、`#inspector-terminology`、`#inspector-citations`（六类引用 mark 按 Unicode code point 切片 + targetNodeId 跳转；越界 mark 显示 `mark out of range` 不抛错）。查看原文/译文即双栏并置，无 pane 内容切换。

## Reader API 与局部重渲染（6.6）

`apps/api`（stdlib ThreadingHTTPServer，无 web 框架）：

- `GET /api/health`：与 `/health` 同 payload；前端启动探测，`apiAvailable` 才渲染 `#retranslate-button`。
- `POST /api/retranslate` body `{"nodeIds": [...]}`：200 `{"ok": true, "changed": [...], "revision": "..."}`；非法 body/未知节点/负 `Content-Length` 400；workspace 未初始化 409；`Content-Length` > 4096 字节 413；声明长度超过实际正文时读取超时 408；真实 workspace 缺失 provider 配置 503；其余异常 500。lualatex 输出目录共享，`threading.Lock` 串行化重渲染。

`pdf_pipeline.pipeline.rerender_workspace(workspace_dir, viewer_data_dir=…, node_ids=…)`（FR-TRANS-004：零源 PDF 重解析）：载入 workspace 六份 canonical 文档 → 校验 `node_ids ⊆ translation.entries` 键集 → 用**当前** provider 身份 `retranslate_nodes`（所选节点跳过缓存读取）→ compose → LaTeX 投影 + 暂存编译 → `recover_render_anchors` → 复用旧 mapping 的 source 侧绑定重建 MappingBundle → 校验通过后发布 viewer revision，再写 workspace 三份文档。真实 workspace 缺失 provider 时失败，不用 dummy 覆盖。注意重新投影意味着整文档 target 重编译（lualatex 秒级~几十秒），这是有意的代价集中。

前端接线：vite dev/preview 把 `/api` proxy 到 `:8000`，并把 `/data/*` 从 `public/data` 按请求提供；`just serve-reader` 一次起 API + dev server（Playwright webServer 用同一命令）。`main.ts` 只负责启动；`DualPaneReader` 拥有 pane 生命周期、导航与重译状态。重译成功后：按新 manifest 加载候选 mapping/meta/PDF（revision URL 失败则回退稳定别名），成功才切换并销毁旧 target document；失败保留旧阅读状态。状态行 `Node re-translated · <id 前 8 位> · <revision 前 8 位>`，`#viewer` 的 `data-busy` / `data-revision` 供 e2e 等待 busy→idle。

正确性修复：[M6 Review 修复](../../.agents/notes/implemented/bug-fix/2026-09-11-m6-review-repairs.md)。

## 夹具

`just viewer-fixture` 用 `tests/fixtures/source/latex/build/paper-anatomy.pdf`（2 页、figure/table/equation/footnote/bibliography 全元素）跑管线产出 `apps/web/public/data/`；该包是 e2e 的全部数据来源（gitignored）。多 fragment 断言依赖其真实跨页 RenderAnchor。

- M6 落地决策：[`.agents/notes/implemented/feature/2026-09-11-m6-bidirectional-reader.md`](../../.agents/notes/implemented/feature/2026-09-11-m6-bidirectional-reader.md)
- 渲染链：[`rendering.md`](rendering.md)
- 映射链：[`source-mapping.md`](source-mapping.md)
