# Agent Note: M8 批次 B 本地 Job 编排、失败归因与手动重试

Status: implemented

[中文](./2026-09-14-m8-batch-b-job-orchestration.md) | [English](./2026-09-14-m8-batch-b-job-orchestration.en.md)

## 问题

[M8 准入收口](../process/2026-09-12-m8-admission-closeout.md) 的批次 B 要求：`apps/api` 暴露任务状态（不只是 `POST /api/retranslate`）、`apps/worker` 从 liveness stub 变成真正执行 pipeline 的 worker、失败要写出 Issue 且任务可重试、进程被杀后按批次 A 的阶段状态继续且不丢已完成产物。批次 A 落地时只有**单个** workspace 的阶段状态（`workspace.json`），没有队列、没有任务生命周期、没有跨 workspace 串行、没有失败归因。批次 C（缓存）、D（失败隔离）、E（真实 parser / 迁移）都需要先有一个可查询、可重试的 Job 层。

## 决策

1. **Job 存储放 `pdf_pipeline.jobs`（新增模块），不放 `apps/`**。`apps/api`、`apps/worker` 只做接线；仓库规则要求可复用逻辑不落应用目录。job 记录与锁协议是本地实现细节，**不进冻结 schema**、不走 `just schema`（与批次 A 的 `workspace.json` 同类）。
2. **文件式队列 + 原子 rename**。jobs root（默认 `.jobs/`）下 `queued/`、`running/`、`finished/`、`locks/` 四个目录，每个 job 是 `<jobId>.json`。记录只在目录间以原子 rename 迁移，因此读者永远看不到半写记录；`get_job` / `list_jobs` 按 `queued > running > finished` 去重，崩溃窗口内不出现两份可见记录。
3. **`flock` 认领 + 内核级死亡检测**。`claim_next` 用 POSIX `fcntl.flock` 取两把独占锁：per-job（worker 互斥）与 per-workspace（同 workspace 串行，因 `lualatex` 每 workspace 共用 `build/`）。锁属于 open file description，**进程退出即由内核释放**——`recover_running` 因此能把「持有者已死」（锁空闲 → 重排为 `queued`）与「仍活着」（跳过）区分开，无需心跳、租约或超时猜测。`FileLock` 是唯一的平台替换点（POSIX-only：macOS / Linux / ubuntu CI）。
4. **仅手动重试**。`failed → queued` 只能经 `retry_job`（`attempt + 1`，清空 `stage`/`error`/`issues`）；不做自动重试与退避。重排只回退 Job，**不清 workspace 产物**——实际重跑哪些阶段由批次 A 的 `stage_completed` 判定，因此已完成产物不丢。
5. **worker 并发可配置 N，同 workspace 恒串行**。`JobWorker(concurrency=N)` 的认领数量上界是 N（已认领但未执行的 job 会白占锁）。默认 1，因为本地单文档场景不需要并行；提高默认值只动 `apps/worker` 的 argparse，不影响存储与协议。
6. **阶段归因失败**。`pipeline._execute_stage(stage, action)` 把每个阶段执行包起来，失败抛 `StageExecutionError`（携带 `Stage`）。`run_pipeline` / `rerender_workspace` 签名不变，既有调用点与测试无需改动。
7. **stage → IssueCategory 映射表**（`STAGE_ISSUE_CATEGORIES`）。job 级 Issue 复用冻结的 Issue 分类，不发明 job 私有分类：阶段内失败 severity `ERROR`、`recoverable: true`、`stage` 为阶段名；进入任何阶段前的失败（不支持输入、源不可读）severity `FATAL`、`recoverable: false`、`stage: null`、category `PHYSICAL_EXTRACTION`。Issue 形状必须能过 `document_model.generated.schema_models.Issue` 校验。
8. **job 级 Issue 只存 job 记录**，不追加进 `semantic.json`：否则同一事实有两个真源。文档内 Issue 属批次 D。
9. **HTTP 契约**：`GET/POST /api/jobs`、`GET /api/jobs/<id>`、`POST /api/jobs/<id>/retry`；提交要求绝对路径（`source` 必须已存在）。已知路径方法不符给 405，未知路径给 404；body 上限与 `/api/retranslate` 共用 `MAX_BODY_BYTES`。端点的 `pdf_pipeline` 导入保持惰性，API 启动不加载 pdfium。

当前态文档：[`docs/architecture/storage.md`](../../../../docs/architecture/storage.md)（新增「任务与 Job 记录」小节）与 [`docs/architecture/api.md`](../../../../docs/architecture/api.md)（端点表）。

## 考虑过的替代方案

- **自动重试与退避**：本地单用户场景下会掩盖真实失败、并把瞬时错误与确定性错误混为一谈；失败先写 Issue、由人决定是否重试更符合「可追踪」目标。
- **SQLite 队列（如 `sqlite3` 或 APScheduler）**：多一个运行时依赖与一套迁移路径，而 job 数量是本地个位级、崩溃窗口只需原子 rename 与一把文件锁即可覆盖。
- **TTL / 租约 + 心跳的超时判定**：需要选一个「多久算死」的阈值，阈值以下的真死 job 会滞留、阈值以上会误判慢速（`lualatex` 编译）的活 job；`flock` 由内核在进程退出时释放，判定是精确的。
- **把 job 记录建模进冻结 schema**：job 记录是本地实现细节，且会随批次 C–F 演进（缓存键、Project 分组），冻结流程成本不成比例。
- **不设 per-workspace 锁，靠 `concurrency=1` 兜底**：并发 N 会成为共享 `build/` 的静默数据竞争（`lualatex` 互相覆写），且并发 N 是产品要求的能力。
- **认领不设上界（一次认领全部 queued）**：已认领但排队等执行的 job 会长时间占住 job 与 workspace 锁，其他 worker 无法接手。
- **把 `StageExecutionError` 放 `apps/`**：阶段枚举属 `pdf_pipeline`，归因必须贴着阶段定义，否则 `apps` 需要重新解释阶段语义。
- **失败时清理 workspace 再重试**：会丢掉批次 A 的价值（已完成阶段复用），并把「重试」变成「从头再来」。

## 后果

- `apps/worker` 现在是真正的执行器：`--jobs-root` / `--concurrency` / `--poll-interval` / `--once`，`run_forever` 先 `recover_running` 再轮询；`status()` 保留供 liveness 检查（`test_worker_status.py` 仍有效）。
- `apps/api` 从单一 `POST /api/retranslate` 扩展为可选查询/提交/重试的 Job API，`make_handler` 增加第三个必需参数 `jobs_root`（`--jobs-root`，默认 `.jobs`）。`.jobs/` 已加入 `.gitignore`。
- 崩溃安全边界：进程被杀 → 锁由内核释放 → 下次启动 `recover_running` 重排 → 阶段状态决定重跑范围。若 `_execute` 自身抛异常（`future.result()` 真抛），剩余 claim 在 `finally` 释放，该 job 记录留在 `running/`，同样由下次 `recover_running` 回收——不丢产物、不静默成功。
- 批次 C 可在 `StageExecutionError` / `input_fingerprint` 上扩展缓存键；批次 D 可在 `job_failure_issue` 之外的文档内 Issue 通道上做 specialist 失败隔离；批次 F 若引入 Project 分组，是 job 记录**之上**的新概念，不改 `source`/`workspace`/`viewerDataDir` 字段。
- 已知边界（非缺陷）：翻译配置变化不使 TRANSLATE 阶段失效（批次 C）；`fcntl.flock` 仅 POSIX；提交用显式绝对路径，无 Project 抽象。
- 验证：新增 `test_jobs.py` 16 项、`test_job_worker.py` 6 项、`test_jobs_api.py` 12 项、`test_worker_cli.py` 2 项；`just lint-python`、`just typecheck-python`、`just test-python`（499 passed, 5 deselected）、`just test-ts`（50 passed）、`just docs-fast`、`just check-fast` 全绿；真实 `lualatex` 端到端 CLI 冒烟通过：API 提交 → `worker --once` → 8 阶段 manifest 全 completed 且 `target.pdf` 生成；坏输入 → `FATAL`/`recoverable: false` 的 failed job → retry 202（attempt 2）→ 再 retry 409；对真实 `run_forever` worker 发 SIGKILL（此时 `ingest`/`physical`/`evidence`/`layout` 已提交）→ 记录留在 `running/` → `recover_running` 重排 → `worker --once` 续跑至 succeeded，且 kill 前的产物字节不变。
