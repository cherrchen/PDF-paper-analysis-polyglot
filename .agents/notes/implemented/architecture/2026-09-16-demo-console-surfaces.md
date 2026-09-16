# Agent Note: 演示控制台四表面与悬浮分区面板

Status: implemented

[中文](./2026-09-16-demo-console-surfaces.md) | [English](./2026-09-16-demo-console-surfaces.en.md)

## 问题

[批次 F](./2026-09-16-m8-batch-f-local-e2e.md) 之后，浏览器里唯一的写路径是一个挤在 `#reader-toolbar` 里的路径式导入面板：要试一篇论文必须手填两个绝对路径，看不到已经跑过的 workspace、job 历史，也看不到 worker 是否活着；Semantic Inspector 作为 `flex: 0 0 320px` 的兄弟节点直接吃掉 PDF 的显示宽度，页面本身也不是 fit-width。手绘稿要求「overlay 显示具体区块，不占用 PDF 显示宽度」，即右栏所有信息都应浮在 PDF 之上。

三个新需求同时缺服务端支点：枚举已有 workspace（此前只有 job 队列，没有 workspace 清单）、把浏览器里的字节交给服务端（`POST /api/jobs` 只接受绝对路径）、判断 worker 存活（此前只能从排队长度与 flock 状态猜）。四项范围决定在本轮确认：select 只做只读枚举 + 同步重发布（不写新 stage、不触发 LLM/LaTeX、不需要 worker）；upload 是真上传，workspace 路径由服务端推导；面板形态是右侧悬浮抽屉，完全不占 PDF 宽度；status 新增 worker 心跳文件与 `GET /api/status`。

## 决策

1. **四表面划分来自手绘稿。** `#surface-tabs` 的四个 `role="tab"`（`#tab-upload` / `#tab-select` / `#tab-history` / `#tab-status`）各控制 `#surface-panels` 内的一个 `role="tabpanel"`；`apps/web/src/surface-tabs.ts::bootSurfaceTabs()` 是唯一状态源（点已打开的表面即关闭，最多一个面板可见），`onChange` 供 select / history 刷新列表、status 起停 3 s 轮询。`#inspector` 移入同一列，DOM 顺序固定 upload → select → history → status → inspector，两层面板同时可见时标签面板在上。
2. **悬浮抽屉，不占 PDF 宽度。** `#surface-panels` 绝对定位在 `#reader-body` 右上（`top: 0; right: 0; bottom: 3.5rem; width: min(360px, 34vw)`，容器 `pointer-events: none`、卡片 `pointer-events: auto`），`#inspector` 的旧 `flex: 0 0 320px` 删除。`bottom: 3.5rem` 让抽屉停在每栏右下角 `.page-controls` 之上，`1 / N` 页码与 Previous/Next 恒可点。代价是抽屉会盖住右栏右缘的 region：需要点击 region 的 e2e spec 先 `uncheck("#inspector-toggle")` 规避，产品行为不改（`#inspector-toggle` 默认仍勾选，`viewer-inspector.spec.ts` 的隐藏/恢复用例依赖初始可见）。
3. **fit-width 与比例滚动。** 每栏 `.page-scroll` 只纵向滚动，`.page-stage canvas` 为 `width: 100%; height: auto`，两份 PDF 恒按栏宽缩放、无横向滚动条。canvas 像素高度因此不再是已知量：`canvasHeight` 从 `reader-overlay.ts::PageMetrics`、`pane-render.ts::RenderCommit` 与 `reader.ts::commitPage` 删除，`scrollFragmentIntoCenter` 与 `syncFrom` 改用 `container.scrollHeight` 比例换算。
4. **upload 真上传，写路径由服务端推导。** `POST /api/uploads` 收原始 PDF 字节（`X-Upload-Name`；流式写 `<jobs-root>/inbox/.{slug}.part` 并累加 sha256，上限 64 MiB，前 5 字节必须是 `%PDF-`），落盘 `<jobs-root>/inbox/{slug}-{sha256 前 8 位}.pdf`，workspace 路径推导成 `<jobs-root>/workspaces/{slug}-{sha256 前 8 位}`（目录由 `run_pipeline` 建）。内容摘要与文件名共同决定文件名：同一文件名 + 同一份 PDF 重复上传复用同一 inbox 文件与同一 workspace。
5. **select 走「读原有产物重发布」，不重跑 stage。** 新增 `pipeline.republish_workspace_viewer(workspace_dir, *, viewer_data_dir)`：只把已提交产物重新发布成新 viewer revision。理由是不能让「打开」有副作用——复用 job 重跑会经 `run_pipeline` 的阶段缓存键判定，配置一漂移就触发真实 provider 调用与整文档 LaTeX 重编译（分钟级、花钱、可能产出不同译文）。前端 `Open` 因此是 `POST /api/workspaces/open` + `DualPaneReader.load()`，而不是提交 job。
6. **`republish_workspace_viewer` 不写 workspace。** 它不调 `commit_stage`、不写 `viewer-publication.json`，只在 viewer 目录写新 revision 并原子翻 manifest；INDEX 的发布回执因此仍由 `run_pipeline` / `rerender_workspace` 独占。target 侧锚点由 `recover_render_anchors(target.pdf, semantic)` 现场恢复（canonical mapping 只带 source 侧绑定）。前置条件是除 INDEX 外每阶段 `artifacts_intact` 且 `mapping.json` 存在，否则抛 `WorkspaceError`。
7. **worker 心跳取代从队列推断存活。** `<jobs-root>/worker.json` 六键（`heartbeatVersion` / `pid` / `startedAt` / `updatedAt` / `concurrency` / `running`），`run_forever` 每 2 s（`HEARTBEAT_INTERVAL_S`）用 daemon 线程原子重写，`run_once` 与正常退出即删；`GET /api/status` 以 `ageSeconds <= HEARTBEAT_STALE_S`（15 s）判 `alive`。心跳写失败只被吞掉，绝不让 worker 死。
8. **两个新写端点的读写边界。** `POST /api/workspaces/open` 只接受**读**来源（一个绝对 workspace 路径，且必须已有 `workspace.json`），写目标恒为服务端自己的 `--data-dir`；`POST /api/uploads` 同理只收字节，inbox 与 workspace 都由服务端命名。这与 `/api/retranslate` 按当前 manifest 绑定选择文档、不接受客户端写路径是同一条规则。

## 考虑过的替代方案

- **抽屉改成占宽的右列。** 手绘稿明确要求不占 PDF 宽度；占宽会让每栏页宽缩水，与 fit-width 目标直接冲突。遮挡代价改由 e2e 侧取消勾选规避，而不是把抽屉变回占宽布局。
- **select 复用 `POST /api/jobs` 重跑同一 workspace。** 见决策 5；此外 job 记录会把「只是打开」写成一次真实运行，history 表面随之失真。
- **select 复用 `rerender_workspace`（零源重解析的重译链）。** 它仍要 provider 调用与整文档 LaTeX 重编译（秒级~几十秒），对「打开」而言是不必要的副作用。
- **`#inspector-toggle` 默认不勾选。** 更少遮挡，但 `viewer-inspector.spec.ts` 的隐藏/恢复用例依赖初始可见，且 region 信息是本产品的主证据面板，默认关等于把证据藏起来。
- **`GET /api/status` 从队列长度与 flock 推断 worker 存活。** 队列为空时无法区分「worker 空闲」与「worker 没起」，flock 只能说明曾有进程持锁。显式心跳是唯一能区分二者的信号。
- **上传落盘到客户端指定的目录。** 那等于把服务端的写目标交给调用方；`inbox/` 与 workspace 名都由内容摘要派生，客户端只提供文件名与字节。

## 后果

- `apps/api`：新增 `paper_api/workspaces.py`、`uploads.py`、`status.py`；`__main__.py` 加 `/api/workspaces`、`/api/workspaces/open`、`/api/uploads`、`/api/status` 四条路由、对应 405 集合与上传专用的连接读超时，`make_handler(workspace, data_dir, jobs_root)` 签名不变。
- `pdf-pipeline`：新增 `workspace.{WorkspaceSummary, summarize_workspace, discover_workspaces}` 与 `WorkspaceManager.{load, artifacts_intact}`（全部不写盘）、`pipeline.republish_workspace_viewer`、`jobs` 心跳常量与函数（`HEARTBEAT_STALE_S = 15.0`）。`apps/worker` 无需改代码，`paper_worker.status()` 保持不动。
- `apps/web`：`index.html` 整文件替换（保留全部既有 id，`#inspector-toggle` 由 button 改为 checkbox），新增 `surface-tabs.ts` / `select-panel.ts` / `history-panel.ts` / `status-panel.ts` / `jobs-client.ts`，`reader.ts` 删 `canvasHeight` 并改用比例滚动，`main.ts` 启动 tabs 与四个面板。
- e2e：新增 `console-surfaces.spec.ts`（四表面开合、`API ok`、history 非空、select 里 `Open` 后 `#viewer` 的 `data-revision` 变化）；需要点击 region 的既有 spec 先 `uncheck("#inspector-toggle")`。
- 文档：控制台表面见 [`reader.md`](../../../../docs/architecture/reader.md)（取代批次 F 的导入面板一节），端点见 [`api.md`](../../../../docs/architecture/api.md)，inbox / 心跳 / 原样重发布见 [`storage.md`](../../../../docs/architecture/storage.md)，§F 的落地措辞见 [`m8.md`](../../../../docs/development/m8.md)。
- 遗留：`republish_workspace_viewer` 每次调用都发布新 revision（即使该 workspace 已是 current），代价约 1.5 MB 写入；换来的是「点 Open 的结果永远可观察」。若将来要省这次写入，判据是 `_viewer_current(workspace_dir, viewer_data_dir)`，但要同时接受「点 Open 后 revision 不变」。若某个历史 workspace 的产物不完整，`Open` 返回 400 且错误串带缺失阶段名，恢复路径是 history 的 `Retry` 或重跑上传 —— 不实现自动修复。

并发与绑定前提见 [P1 修复 note](../bug-fix/2026-09-16-m8-p1-concurrency-and-binding.md)；job 记录与队列语义见 [批次 B note](./2026-09-14-m8-batch-b-job-orchestration.md)；M6 的跳转与 overlay 契约见 [M6 note](../feature/2026-09-11-m6-bidirectional-reader.md)。
