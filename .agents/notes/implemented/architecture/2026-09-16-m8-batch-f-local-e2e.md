# Agent Note: M8 批次 F 本地产品端到端验收

Status: implemented

[中文](./2026-09-16-m8-batch-f-local-e2e.md) | [English](./2026-09-16-m8-batch-f-local-e2e.en.md)

## 问题

[`docs/development/m8.md`](../../../../docs/development/m8.md) §F 要求 PRD §40 的产品流——导入 PDF → 分析 → 翻译 → Target PDF → Source/Target 跳转——在**运行中的本地栈**上端到端走通，并要求「发布失败后 viewer 仍读到上一修订」在产品层被证明，而不只是 `packages/python/pdf-pipeline/tests/test_rerender_workspace.py` 里的 monkeypatch 单元测试。批次 A–E 之后栈的实际形态是：`paper_api`（:8000）+ Vite dev（:4173，`servePublicData` 插件按请求流式读 `apps/web/public/data`，`/api` 反代 :8000）；`paper_worker` 存在但除手动 `just dev-worker` 外没有任何东西启动它；viewer 是只读 fixture 阅读器，唯一写路径是 `POST /api/retranslate`。

三个缺口。第一，产品没有导入表面：Job API（批次 B）只能靠 curl 提交，浏览器里没有任何入口。第二，即使加了提交入口，`POST /api/jobs` 的契约要求提交方给出绝对 `viewerDataDir`，浏览器不知道该填什么——Vite 服务的是 API 进程自己的 `--data-dir`，填错就把修订发布到没人读的地方。第三，「发布失败仍读上一修订」只在单元层证明：注入点是 `_commit_prepared_file`（docstring 已写明 "a seam for publish fault injection"），但外部进程无法触发它——没有任何 env 或参数能让一次真实 HTTP 发布中途失败。

## 决策

1. **导入表面 = 最小路径式面板，不做上传。** `apps/web/src/import-panel.ts` 导出 `bootImportPanel(reader)`：两个文本输入（绝对 `source` / `workspace` 路径）+ 提交按钮 + `aria-live` 状态区，走 `POST /api/jobs` → 每 2 s 轮询 `GET /api/jobs/<id>` → `succeeded` 后调 `reader.load()` 就地换修订。理由：PRD §40 没有上传；`MAX_BODY_BYTES=4096` 与绝对路径 Job 契约是批次 B 的地基，为面板引入 multipart/落盘临时文件等于第二套契约。客户端只做「非空且以 `/` 开头」的前置校验（本地产品 POSIX-only，与批次 B 的 `fcntl.flock` 假设同一前提），服务端 `parse_job_request` 的校验一字不改。
2. **API 新规则：省略（或 `null`）`viewerDataDir` ⇒ 默认取服务端自己的 `--data-dir`。** `handle_submit_job` 增 keyword 参数 `default_viewer_data_dir: Path | None = None`，`parse_job_request` 之后 `viewer_data_dir = viewer_data_dir or default_viewer_data_dir`；`__main__.do_POST` 传 `data_dir`。202 响应携带生效目录，提交方看得见实际值。显式值照旧必须是绝对路径——默认只补缺省，不放松校验。没有这条规则，浏览器提交的作业会把修订发布到 worker 进程 `run_pipeline` 的 `viewer_data_dir=None` 缺省路径（workspace 内 `viewer/data/`），而 Vite 流式的是 API 的 `--data-dir`，viewer 永远看不到新修订。
3. **worker 传目录：验证后确认无需改动。** `JobWorker._run_job` 已经 `Path(job.viewer_data_dir) if job.viewer_data_dir else None` 传给 runner 第三位置参数；本批只补 `test_worker_passes_record_viewer_data_dir_to_runner` 把这条链钉死（record → runner 实参）。
4. **viewer 就地换修订：`DualPaneReader.load(revisionBust)`。** 复用 `retranslate()` 里已验证的成功路径形状：`fetchViewerManifest({ cacheBust, fallback: false })` → `loadViewerAssets(…, { includeSource: true })` → 整体赋值 `meta/model/revision/pdfs` 两侧 → 双 `currentPage=-1`、`setViewerChrome()`、两栏 `showPage(0)` → 销毁两个旧 `PDFDocumentProxy`。候选加载失败时原状态一个字节都不动、直接 rethrow，由调用方显示状态——不需要 `retranslate()` 那套回滚舞步，因为 `manifest.json` 就是提交指针，失败的换页不触碰它。`retranslate()` 行为不改。
5. **发布故障注入 = 文档化 env 缝：`PAPER_PUBLISH_FAULT=<file name>`。** `pdf_pipeline/config.py` 新增 `PUBLISH_FAULT_ENV` + `load_publish_fault()`（沿用批次 E 的 `REGISTRY_PATH_ENV` 约定）；`_commit_prepared_file` 在 `staged.replace(target)` 之前比对 `target.name`，命中即 `raise OSError(f"publish fault injected for {target.name}")`。它是纯配置面 env，不进缓存键（不改任何产物字节），未设 ⇒ 逐字节无行为变化。选择 env 而不是新 HTTP 端点或 CLI flag：缝要在**发布事务内部**、在任意真实进程（pytest、e2e 起的 API）里生效，而发布发生在 worker/API 进程深处，调用方没有函数指针可递。
6. **`PAPER_VIEWER_DATA_DIR`：Vite `/data` 根目录覆盖。** `servePublicData()` 的数据根改为 `process.env.PAPER_VIEWER_DATA_DIR ? path.resolve(env) : path.resolve(publicDir, "data")`；越权防护、content-type、流式行为不变，未设 ⇒ 与今天逐字节一致。存在的唯一理由：故障路径的 e2e 要在**不碰主流栈正在服务的 `apps/web/public/data`** 的前提下，用 fixture 数据的副本起第二个真实 API + 第二个 Vite 做产品级证明。
7. **worker 进 `serve-reader`；Playwright 串行。** 本地栈 recipe 与 playwright `serveCommand` 同步扩成三进程（API + worker + vite，`--jobs-root .jobs` 两边都显式钉住，注释约定二者保持一致）。`fullyParallel: true` → `false` + `workers: 1`：一旦浏览器提交的作业会向被服务的数据根发布新修订，`apps/web/public/data` 就成了共享可变状态，其它 spec 同时在读/翻 manifest，串行是唯一不引入跨 spec 修订竞态的做法。`product-import.spec.ts` 自己再套一层保险：提交前快照 `public/data`、`finally` 里逐字节恢复，因为后续 viewer-* spec 断言的正是 anatomy fixture。
8. **两个 e2e spec 是产品层的对应证明。** `tests/e2e/product-import.spec.ts`：真实三进程栈 + 真实 lualatex，tikz-vector（不同于 anatomy 的 PDF）从浏览器进、worker 排队执行、面板轮询到 `succeeded`、viewer 换到 Job 发布的新修订（`data-revision` 变化、target 页数 ≠ anatomy 页数）、双向点击跳转在新修订上通过。`tests/e2e/publish-failure.spec.ts`：复制数据根 + workspace，起带 `PAPER_PUBLISH_FAULT=target.pdf` 的第二个 API（:8010），HTTP `POST /api/retranslate` 得到 500 + `publish fault injected`，磁盘断言 manifest/四个稳定别名与 `revisions/` 集合与基线**逐字节相同**，然后 `PAPER_VIEWER_DATA_DIR` 指到副本数据根起第二个 Vite（:4183），浏览器在上一修订上 boot 并完成一次往返跳转。断言清单对齐 `test_rerender_mid_publish_failure_rolls_back_viewer_and_workspace`，不发明新不变量。

## 考虑过的替代方案

- **上传端点 + 临时落盘**：需要 multipart 解析、大小/类型策略、清理生命周期，全部在批次 B 的 4 KB JSON 契约之外；PRD §40 也没要求。路径式面板与 Job 契约同形。
- **面板把 `viewerDataDir` 填成 `/` 或从 `/api/health` 猜**：健康端点不暴露数据目录；让浏览器猜一个写进磁盘的绝对路径是静默发错地方的邀请。默认规则把真相留在唯一知道它的进程里（API 自己的 `--data-dir`），且 202 回显生效值。
- **`load()` 复用 `retranslate()` 的回滚逻辑**：`retranslate()` 要回滚是因为服务端**已经**发布了新修订、失败发生在换页中途；`load()` 的失败只可能发生在候选加载阶段，此时状态还没动。为对称性复制那套 try/catch/finally 舞步是无观测差异的管线。
- **故障注入做成 `POST /api/debug/publish-fault`**：给生产 API 加一个能故意弄坏发布的端点，换来的是攻击面；env 缝只在显式设置它的进程里存在。
- **e2e 用 monkeypatch 假 worker / 假 runner 证明产品流**：§F 验收的对象就是真实链条（队列、flock、lualatex、发布事务），假 runner 证明的是已经证明过的单元。
- **两个 e2e 保持并行、给每个 spec 独立数据根**：独立数据根要么改 `servePublicData` 成 per-request 可切换（复杂化主流栈），要么每个 spec 起自己的三进程栈（端口/资源翻倍）。串行 + 快照恢复是最小且充分的做法；竞态根因（共享可变发布目标）本来就是用例设计的一部分。
- **`PAPER_PUBLISH_FAULT` 入缓存键**：它不改变任何成功发布的产物字节（命中即无发布），入键只会让故障调试本身引发重跑。

## 后果

- `packages/python/pdf-pipeline/src/pdf_pipeline/config.py`：新增 `PUBLISH_FAULT_ENV`、`load_publish_fault()`；模块 docstring 扩为「批次 E 与 F 的操作者环境配置」。
- `packages/python/pdf-pipeline/src/pdf_pipeline/pipeline.py`：`_commit_prepared_file` 查缝（+2 行）；import 行加 `load_publish_fault`。未设 env 时发布路径字节级不变——既有 `test_rerender_workspace.py` 全部用例零修改通过即为证明。
- `apps/api`：`jobs.py` `handle_submit_job` 增 `default_viewer_data_dir`，`__main__.py` 传 `data_dir`。
- 测试（Python）：`test_parser_config.py` +3（env 未设/空串/读取）；`test_rerender_workspace.py` +3（缝在 `_replace_files_with_rollback` 内触发且已换别名回滚、manifest 故障时旧文件恢复且 manifest 不诞生、`_publish_viewer_revision` 故障时前一修订逐字节完好且 staged `revisions/<id>/` 被删）；`test_job_worker.py` +1（record → runner 第三实参）。文件头 `reportPrivateUsage=false`（与 `test_job_worker.py` 既有约定一致）。
- `apps/web`：`reader.ts` 新增 `load()`；新模块 `import-panel.ts`（+ `import-panel.test.ts` 5 例：离线禁用、提交体 `{source, workspace}`、轮询到 succeeded 后恰一次 `load`、failed 渲染 stage/error 且不换页、load 失败保留上一修订、相对路径不碰 API）；`index.html` 工具栏内 `#import-panel` 表单；`viewer.css` 面板样式；`main.ts` 在 `reader.start()` 后 `bootImportPanel(reader)`。
- `apps/web/vite.config.ts`：`servePublicData` 数据根读 `PAPER_VIEWER_DATA_DIR`。
- `justfile` `serve-reader` 与 `playwright.config.ts` `serveCommand`：三进程；`fullyParallel: false` + `workers: 1`。
- `apps/web`：`reader.ts` 新增 `load()`；新模块 `import-panel.ts`（+ `import-panel.test.ts` 6 例：离线禁用、提交体 `{source, workspace}`、轮询到 succeeded 后恰一次 `load`、failed 渲染 stage/error 且不换页、load 失败保留上一修订、相对路径不碰 API）；`index.html` 工具栏内 `#import-panel` 表单；`viewer.css` 面板样式；`main.ts` 在 `reader.start()` 后 `bootImportPanel(reader)`。
- 文档：`docs/architecture/api.md`（submit 体默认规则）、`reader.md`（导入面板流、`load()`、`PAPER_VIEWER_DATA_DIR`、栈含 worker）、`storage.md`（发布事务段点名 `PAPER_PUBLISH_FAULT`）、`docs/development/m8.md` §F 落地段、roadmap 与 README 状态行；英文伴侣同步。
- 观察到的行为：`just test-e2e` 七个 spec 全绿；手动栈冒烟里 `POST /api/jobs`（无 `viewerDataDir`）返回 `"viewerDataDir":"apps/web/public/data"`，worker 执行 `succeeded`，:4173 上 manifest 翻到新修订。
- 遗留：真机浏览器手动验收（面板 UX 细节）未单独做，交互路径全部由 e2e 覆盖；`reuseExistingServer` 下若残留旧手工 worker，flock 序列化保证结果确定，无需处理。
