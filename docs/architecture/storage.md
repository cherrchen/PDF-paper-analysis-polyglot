# 存储

[中文](./storage.md) | [English](./storage.en.md)

持久对象存储、制品布局与数据集托管**有意未决**；本地 Project / Document Workspace 与任务编排约定已分别由 [M8 初版批次 A / B](../development/m8.md) 收口，见下。

## 本地 workspace（M8 批次 A，已收口）

`run_pipeline(source_pdf, out_dir)` 把 `out_dir` 变成一个**可恢复的本地 workspace**。目录布局：

```text
<workspace>/
  workspace.json          # ad-hoc 清单（与 probe.json 同类，不进冻结 schema）
  source.pdf              # INGEST 保留的源 PDF 字节
  physical.json …         # 各阶段 canonical JSON 产物
  probe.json              # 探测 + routing 诊断（ad-hoc）
  evidence-bundles.json   # 各 provider bundle 的 ad-hoc 持久化
  resources/              # 图像与 figure PDF fragment
  target.pdf              # committed render artifact
  viewer-publication.json # viewer destination and publication hashes
  build/                  # LaTeX 编译产物（target.pdf），非清单产物
  viewer/data/            # viewer revision（沿用既有发布事务）
```

### 阶段与提交协议

阶段枚举：`INGEST → PHYSICAL → EVIDENCE → LAYOUT → SEMANTIC → TRANSLATE → RENDER → INDEX`（`pdf_pipeline.workspace`）。

- 每阶段在 `workspace.json` 记录：status、产物相对路径 + sha256、producer 版本、输入指纹（生产者版本 + 上游产物哈希）。
- 提交顺序：产物先写入 `.staging/`，逐文件原子 replace，最后原子重写 `workspace.json`——清单是**唯一提交指针**。
- 恢复：`stage_completed` 为真（COMPLETED + 产物哈希校验通过 + 输入指纹与上游记录一致）才跳过；否则重跑该阶段。中断后重启只重跑未完成阶段；半写入目录永远不会被当成成功。
- 源绑定：manifest 的 `sourceFingerprint` 锁定源 PDF；未知 `workspaceVersion` 与外来源 PDF 一律明确报错（迁移属批次 E）。

权威实现：`packages/python/pdf-pipeline/src/pdf_pipeline/workspace.py` 与 `pipeline.py` 的阶段 runner；决策理由见 Agent Note `2026-09-12-m8-batch-a-workspace-stages`。

### 当前边界

- `workspace.json` 是 ad-hoc 文件，schema 变更不走 `just schema` 冻结流程。
- 翻译配置变化导致的阶段失效与跨配置缓存键属批次 C；本版恢复只按上游产物哈希判断。
- viewer revision 发布沿用 `_publish_viewer_revision` 事务，不在清单内逐文件追踪。

## 任务与 Job 记录（M8 批次 B，已收口）

`pdf_pipeline.jobs` 把「一次 workspace 运行」包成可提交、可查询、可重试的 **Job**，应用侧（`apps/api`、`apps/worker`）只做接线。jobs root 默认 `.jobs/`：

```text
<jobsRoot>/
  queued/    <jobId>.json     待认领
  running/   <jobId>.json     已被存活的 worker 认领
  finished/  <jobId>.json     终态（succeeded / failed）
  locks/     job-<jobId>.lock 与 workspace-<workspaceHash>.lock
```

Job 记录字段：`jobVersion`（当前 `0.1.0`）、`id`（32 位小写 hex）、`status`、`source`、`workspace`、`viewerDataDir`、`attempt`（从 1 起）、`createdAt`、`updatedAt`、`stage`、`error`、`issues`。记录以原子 rename 在三个目录间迁移；`get_job` / `list_jobs` 按 `queued > running > finished` 去重，崩溃窗口内不会出现两份可见记录。未知 `jobVersion`、非法 `id`、无法解析的记录一律明确报错。

### 状态机与认领

- `queued → running → succeeded | failed`；`failed → queued` 仅经手动 `retry_job`（`attempt + 1`，清空 `stage` / `error` / `issues`）。`error is None` 即 `succeeded`。**无自动重试与退避。**
- `claim_next` 按 `(createdAt, id)` 取最旧的 queued job，并用 POSIX `fcntl.flock` 取两把锁：per-job 锁保证 worker 间互斥，per-workspace 锁保证同一 workspace 的 job 串行（`lualatex` 每 workspace 共用 `build/`）。
- `flock` 属于 open file description：进程退出即由内核释放。`recover_running` 因此能区分「持有者已死」（锁空闲 → 重排为 `queued`，`attempt` 不变）与「仍活着」（锁被持有 → 跳过）。worker 并发数 `--concurrency` 可配置（默认 1）：不同 workspace 可并行，同 workspace 恒串行。
- 重排只回退 Job，**不动** workspace 产物；实际重跑哪些阶段仍由批次 A 的阶段状态判定，因此已完成产物不丢。

### 失败归因

阶段执行包在 `pipeline._execute_stage` 中，失败抛 `StageExecutionError`（携带 `Stage`）。`JobWorker` 据此写 job 级 canonical Issue：

| 失败位置 | `severity` | `recoverable` | `category` |
| --- | --- | --- | --- |
| 某阶段内（`stage` 为阶段名） | `ERROR` | `true` | `STAGE_ISSUE_CATEGORIES[stage]`（如 SEMANTIC → `SECTION_STRUCTURE`、TRANSLATE → `TRANSLATION`） |
| 未进入任何阶段（`stage: null`） | `FATAL` | `false` | `PHYSICAL_EXTRACTION` |

Issue 形状必须能通过 `document_model.generated.schema_models.Issue` 校验（含 `id`、`producer`、`message`、`affectedIds`）。job 级 Issue **只存 job 记录**，不追加进 `semantic.json`（避免两个真源；文档内 Issue 属批次 D）。

权威实现：`packages/python/pdf-pipeline/src/pdf_pipeline/jobs.py` 与 `pipeline.py` 的 `_execute_stage`；HTTP 契约见 [HTTP API](api.md)；决策理由见 Agent Note `2026-09-14-m8-batch-b-job-orchestration`。

## 仍未决

持久对象存储、多机共享、数据集托管。未来的外部数据集系统需要 testing 或 architecture Agent Note。

保持 Git 历史精简。不要提交大型 PDF 语料。

## 审查修复

恢复时比较当前阶段生产者版本，并读取根目录已提交的 `target.pdf`；`build/` 可删除。INDEX 用发布回执记录 viewer 目标目录、manifest、稳定别名与当前 revision 的哈希，输出缺失或变化时重新发布。局部重译在既有回滚事务中同时发布翻译/渲染阶段记录与根目录目标 PDF，使 INDEX 失效；下一次运行保留新译文。清单写入失败会还原内存阶段记录。理由见 [批次 A 审查修复](../../.agents/notes/implemented/bug-fix/2026-09-12-m8-batch-a-review-repairs.md)。
