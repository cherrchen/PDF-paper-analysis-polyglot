# 阅读器（M6 Bidirectional Reader）

[中文](./reader.md) | [English](./reader.en.md)

双向跳转架构见 [`document-architecture.md`](document-architecture.md) 第 32–33 节。本页描述当前态实现：viewer 数据契约 v2、前端空间索引、导航/滚动/高亮/focus 行为、Semantic Inspector、控制台表面、reader API 与局部重渲染。

## Viewer 数据契约 v2

`pdf_pipeline.pipeline._write_viewer_assets` 是 `viewerDataVersion: 2` 包的唯一生产者。每次发布先写完整且不可变的 `revisions/<id>/`（`mapping.json`、`viewer-meta.json`、`source.pdf`、`target.pdf`），再以可回滚文件集替换稳定别名与重译产生的 workspace JSON，最后原子替换 `manifest.json` 指向该 revision。中途失败恢复全部已替换文件并删除未发布 revision。阅读器始终整组加载同一 manifest 的 URL；仅在首次启动缺少 manifest 时整组使用稳定别名，不做单文件回退。dev/preview 通过 `serve-public-data` 插件按请求从 `public/data` 读盘，避免把 `/data/*` 交给 SPA fallback。canonical MappingBundle 字段照常展开（schema 保持 `mapping` 0.1.0，零变更），并附 viewer 私有投影：

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

`apps/web/src/mapping.ts` 的 `Pair = { sources: Fragment[]; targets: Fragment[] }` 收集双侧全部 fragments（多 fragment 是一等公民）。节点身份来自绑定。`pickCounterpart(pair, origin, originRect)` 是 Initial Product 下的**节点内落点启发式**（PRD 不要求字符级 mapping）：在对侧「不小于 origin 页码」的最小页上取 y 最近者；不存在则取对侧第 0 个。它不承担 FR-SYNC-004 的身份判定。点击选择走空间索引 `hitTest`（最小面积优先）；键盘激活仍使用获焦按钮对应的 fragment。

`apps/web/src/reader.ts` 的 `DualPaneReader.activate(nodeId, origin, fragment)`：

1. destination pane 渲染 `pickCounterpart` 所在页（每侧 `PaneRenderer` 取消旧 PDF.js 任务，只提交最新 generation；同页请求也先废弃未提交的旧翻页，再重画 overlay）；
2. 按 `(fragment 中线 pt / 页高 pt) × container.scrollHeight` 把该 fragment 滚到 pane 视口中线（clamp；fit-width 后 canvas 像素高度不再是已知量，见「控制台表面」）；
3. 对 destination 的 overlay 按钮 `focus({preventScroll:true})`；
4. origin 侧重绘保留 `aria-pressed` 选中态；active 态跨翻页保留。选中态经 `setActiveNode` 统一更新 overlay 与 Inspector。

同步滚动（`#sync-scroll` checkbox，默认关）：滚动侧视口中线 ±12 pt 条带 `inBand` 查询 → 首个含 paired 节点的命中 → `pickCounterpart` → 对侧渲染并滚动到位；视口中线由 `(scrollTop + clientHeight / 2) / scrollHeight × 页高 pt` 反算（fit-width 比例换算，不是 canvas 像素）。查不到节点时什么都不做（禁止页码猜测回退）。程序性滚动后 250 ms 内忽略对侧 scroll 事件防回环。

## Semantic Inspector（6.5）

`apps/web/src/inspector.ts::renderInspector(root, model, nodeId, opts)`。面板含稳定 id（e2e 选择器）：`#inspector-node-id`（完整 SemanticNodeID）、`#inspector-kind`、`#inspector-anchors`（`source p{n} [x,y w×h]` 双侧逐条）、`#inspector-source-text`、`#inspector-translation`（无 entry 显示 `Not translatable`，BIBLIOGRAPHY_ENTRY 按 PRD FR-CITE-004 不进翻译层）、`#inspector-relations`（双向 relation 按钮可跳转）、`#inspector-confidence`（节点 score + reason + target anchor 置信）、`#inspector-provenance`、`#inspector-issues`（有则显示）、`#inspector-terminology`、`#inspector-citations`（六类引用 mark 按 Unicode code point 切片 + targetNodeId 跳转；越界 mark 显示 `mark out of range` 不抛错）。查看原文/译文即双栏并置，无 pane 内容切换。`#inspector` 是悬浮列 `#surface-panels` 里的最后一张卡片，由 `#inspector-toggle`（checkbox，默认勾选）控制显隐：取消勾选即隐藏，节点未选中时面板始终 `hidden`；面板悬浮在 PDF 之上，不占显示宽度。

## Reader API 与局部重渲染（6.6）

`apps/api`（stdlib ThreadingHTTPServer，无 web 框架）：

- `GET /api/health`：与 `/health` 同 payload；前端启动探测，`apiAvailable` 才渲染 `#retranslate-button`。
- `POST /api/retranslate` 由当前修订绑定选择 workspace，并使用跨进程 workspace 锁。请求、状态码和旧客户端兼容规则见 [HTTP API](api.md#重译的文档绑定)，锁顺序见[存储](storage.md#m8-p1-并发修复)。

`pdf_pipeline.pipeline.rerender_workspace(workspace_dir, viewer_data_dir=…, node_ids=…)`（FR-TRANS-004：零源 PDF 重解析）：载入 workspace 六份 canonical 文档 → 校验 `node_ids ⊆ translation.entries` 键集 → 用**当前** provider 身份 `retranslate_nodes`（所选节点跳过缓存读取）→ compose → LaTeX 投影 + 暂存编译 → `recover_render_anchors` → 复用旧 mapping 的 source 侧绑定重建 MappingBundle → 校验通过后写不可变 viewer revision，再把稳定别名、workspace 三份 JSON 与 manifest 纳入可回滚提交。真实 workspace 缺失 provider 时失败，不用 dummy 覆盖。注意重新投影意味着整文档 target 重编译（lualatex 秒级~几十秒），这是有意的代价集中。

前端接线：vite dev/preview 把 `/api` proxy 到 `:8000`，并把 `/data/*` 按请求从数据根提供——数据根默认 `public/data`，设了 `PAPER_VIEWER_DATA_DIR` 时改为其解析结果（批次 F 的发布故障 e2e 用它服务 fixture 数据的副本；未设时行为逐字节不变）。`just serve-reader` 一次起三进程本地栈——API、`paper_worker --jobs-root .jobs`、vite（Playwright webServer 镜像同一命令）。`main.ts` 只负责启动（`reader.start()` 后 `bootSurfaceTabs()`，再依次 `bootImportPanel(reader)` / `bootSelectPanel(reader, tabs)` / `bootHistoryPanel(reader, tabs)` / `bootStatusPanel(reader, tabs)`）；`DualPaneReader` 拥有 pane 生命周期、导航与重译状态。重译成功后：按新 manifest 整组加载候选 mapping/meta/PDF，成功才切换并销毁旧 target document；加载失败保留旧阅读状态，切换后首屏渲染失败则重绘旧 target 页并恢复页码、overlay、focus 与滚动位置。状态行 `Node re-translated · <id 前 8 位> · <revision 前 8 位>`，`#viewer` 的 `data-busy` / `data-revision` 供 e2e 等待 busy→idle。

正确性修复：[M6 Review 修复](../../.agents/notes/implemented/bug-fix/2026-09-11-m6-review-repairs.md)。

## 控制台表面

`apps/web/index.html` 的 `#surface-tabs` 是四个 `role="tab"` 按钮（`#tab-upload` / `#tab-select` / `#tab-history` / `#tab-status`），各自控制 `#surface-panels` 内的一个 `role="tabpanel"`（`#panel-upload` / `#panel-select` / `#panel-history` / `#panel-status`）。`apps/web/src/surface-tabs.ts::bootSurfaceTabs()` 是唯一状态源：点击未打开的表面即 `open(id)`，点击当前已打开的表面即 `close()`（全部面板 `hidden`、全部 tab `aria-selected="false"`），任何时刻最多一个标签面板可见；`onChange` 订阅者据此刷新列表或起停轮询。同一条 tab 栏上还有两个 checkbox：`#sync-scroll`（同步滚动，默认关）与 `#inspector-toggle`（region 信息，默认勾选，见 6.5）。

布局（`viewer.css`）：`#reader-body` 是定位上下文，`#panes` 是两栏 grid；每栏 `.page-scroll` 只纵向滚动（`max-height: 72vh`），`.page-stage canvas` 为 `width: 100%; height: auto`，因此两份 PDF 恒按栏宽缩放（fit-width）、不出现横向滚动条；页码 `1 / N` 与 Previous/Next 钉在每栏右下角的 `.page-controls`（`#source-page` / `#target-page`）。`#surface-panels` 是**绝对定位的右侧悬浮抽屉**（`top: 0; right: 0; bottom: 3.5rem; width: min(360px, 34vw)`，`z-index: 6`，容器 `pointer-events: none`、卡片 `pointer-events: auto`）：标签面板与 region 信息共用这一列，DOM 顺序固定为 upload → select → history → status → `#inspector`，所以两层面板同时可见时标签面板总在 region 信息之上。抽屉**不占用 PDF 显示宽度**，代价是盖住右栏右缘的 region——需要点击 region 的 e2e spec 因此先 `uncheck("#inspector-toggle")` 规避（产品行为不变）。`bottom: 3.5rem` 让抽屉停在页码导航之上，保证 `#source-next` / `#target-next` 始终可点。

视觉层（同一文件的 `:root` 块）：调色板逐值取自 Overleaf 已发布样式表（`https://cdn.overleaf.com/stylesheets/main-style-476eb7ca577de65f3a7b.css`，2026-09-17 抓取），沿用上游 token 名；它是 `viewer.css` 里唯一的颜色真源——`#rrggbb` 只允许出现在该块内，其余一律 `var(--…)` 或由这些 token 派生的 `rgb(… / …)`。页头是 sticky 的白底 `.masthead`：`.brand-mark` 品牌块 + `#title` + `#status` + 绿色主按钮 `#open-upload`（接线到 `surface-tabs.ts::SurfaceTabs.open("upload")`，与点 `#tab-upload` 同一条状态机路径）。UI 字体是系统 sans 栈，monospace 只留给标识符 / 路径 / 页码几何；`.pane` 由阴影改为 1px 分隔线 + `--radius` 圆角，`.page-scroll` 为浅灰底、`.page-stage canvas` 自带 1px 边框与白底，悬浮 region 常态蓝、hover 加深、选中转绿（`aria-pressed="true"`）。tab 栏上的两个 checkbox 仍是原生 `input`（自绘外观为 `appearance: none` + 勾选态绿色背景），e2e 的 `check` / `uncheck` 不受影响；上述几何事实（抽屉位置与尺寸、fit-width、比例滚动、`bottom: 3.5rem`、`max-height: 72vh`）未改。

fit-width 之后同步滚动与跳转不按 canvas 像素换算：`scrollFragmentIntoCenter` 用 `(fragment 中线 pt / 页高 pt) × container.scrollHeight` 定位并 clamp 到 `scrollHeight - clientHeight`，`syncFrom` 用 `(scrollTop + clientHeight / 2) / scrollHeight × 页高 pt` 反算中线；±12 pt 条带、`pickCounterpart` 与 250 ms 抑制不变。

- **upload**（`#panel-upload`）：`#upload-drop` 拖放或 `#upload-file` 选择文件 → 非 `.pdf` 直接拒绝 → `jobs-client.ts::uploadPdf()` 走 `POST /api/uploads`（头部 `X-Upload-Name`，body 即文件字节）→ 服务端返回的 `path` / `workspace` 填入 `#import-source` / `#import-workspace`，`#upload-status` 显示 `Uploaded <bytes> bytes · <path>`，随即走一次与 `#import-submit` 相同的提交路径自动开工。路径式表单（绝对 `source` / `workspace` + 提交按钮，`apiAvailable` 为 false 时禁用并显示 `Import unavailable · API offline`）保留：`jobs-client.ts::submitJob()` 发 `{"source","workspace"}`——不带 `viewerDataDir`，服务端默认成自己的 `--data-dir`，也就是本 viewer 读取的目录——再 `followJob()` 每 2 s 轮询 `GET /api/jobs/<id>` 到终态（无客户端截止：真实论文在真实 provider 上要跑分钟级，提前放弃会让阅读器停在上一修订；运行中状态行 `Job <status> · <id 前 8 位> · 已用时`）。`succeeded` 时调 `DualPaneReader.load(String(Date.now()))` 就地换到 Job 发布的修订；换页失败时上一修订完好无损，显示 `Reload failed · …`。`failed` 时显示 `Job failed · <stage ?? "fatal"> · <error 前 160 字符>`，不触碰阅读器。
- **select**（`#panel-select`）：`GET /api/workspaces` 列出 `discover_workspaces(jobs_root, extra=(API 自己的 workspace,))` 的摘要（name / 完整 path / `<已完成数>/8 stages committed`（存在 `degraded` 时追加）/ updatedAt / error），当前发布的那条标 `data-current="true"`；`complete === false` 或 `error !== null` 的行 `Open` 禁用。`Open` → `POST /api/workspaces/open`（body `{"workspace": "<绝对路径>"}`）→ 服务端 `republish_workspace_viewer()` 把该 workspace **已提交的产物**原样重发布成新 revision（不跑 stage、不写 workspace）→ 成功后 `reader.load()`，状态写 `Opened · <revision 前 8 位>`。API 不可用时列表清空并显示 `Workspace list unavailable · API offline`。
- **history**（`#panel-history`）：`GET /api/jobs` 按 `createdAt` 倒序列出 job 记录（status / `attempt <n>` / stage / updatedAt / source 与 workspace 绝对路径 / error 前 160 字符）；`failed` 行给 `Retry`（`POST /api/jobs/<id>/retry` 后刷新列表），`succeeded` 行给 `Open`（select 的同一条重发布 + `reader.load()` 路径）。
- **status**（`#panel-status`）：面板打开时每 3 s 轮询 `GET /api/status`，渲染四行——API（成功为 `API ok · <origin>`，即 `GET /api/health` 探测通过）、worker 心跳（`Worker running · pid <pid> · <running> job(s) · heartbeat <age>s`，心跳过期显示 `Worker stale · last heartbeat <age>s ago`，无心跳显示 `Worker not detected · start just dev-worker`）、job 计数（`Queued n · Running n · Succeeded n · Failed n`，`queued > 0` 时追加为 `… · Failed n · oldest queued <oldestQueuedAt>`）、viewer 发布（`Revision <revision 前 12 位> · workspace <workspace ?? "unknown">`，再附 reader 本地事实：`source n pages` / `target n pages` / `<n> linked regions`，有选中节点时附 `active <id 前 8 位>`；无发布时为 `No published revision`）。API 不可达时只显示 `API unreachable · <status 或 error>` 并清空其余三行。

四条新端点（`GET /api/workspaces`、`POST /api/workspaces/open`、`POST /api/uploads`、`GET /api/status`）的请求、状态码与读写边界见 [HTTP API](api.md)；`<jobs-root>/inbox/` 文件名规则、worker 心跳六键与 `republish_workspace_viewer` 的「不写 workspace」契约见[存储](storage.md)。`tests/e2e/console-surfaces.spec.ts` 覆盖四表面的开合、`#status-api` 的 `API ok`、history 列表非空，以及 select 里 `Open` 之后 `#viewer` 的 `data-revision` 变化。

导入/打开切换的首屏属于候选准备阶段：双侧先离屏渲染，并等待两侧结束；成功才提交状态与画面、销毁旧 PDF。getPage 或 render 失败只销毁候选 PDF，旧阅读状态与画布不变。

## 夹具

`just viewer-fixture` 用 `tests/fixtures/source/latex/build/paper-anatomy.pdf`（2 页、figure/table/equation/footnote/bibliography 全元素）跑管线产出 `apps/web/public/data/`；该包是 e2e 的全部数据来源（gitignored）。多 fragment 断言依赖其真实跨页 RenderAnchor。

- M6 落地决策：[`.agents/notes/implemented/feature/2026-09-11-m6-bidirectional-reader.md`](../../.agents/notes/implemented/feature/2026-09-11-m6-bidirectional-reader.md)
- 渲染链：[`rendering.md`](rendering.md)
- 映射链：[`source-mapping.md`](source-mapping.md)
