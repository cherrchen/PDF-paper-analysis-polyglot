# 存储

[中文](./storage.md) | [English](./storage.en.md)

持久对象存储、制品布局与数据集托管**有意未决**；本地 Project / Document Workspace 与任务编排约定已分别由 [M8 初版批次 A–E](../development/m8.md) 收口，见下。

## 本地 workspace（M8 批次 A / C / D / E，已收口）

`run_pipeline(source_pdf, out_dir)` 把 `out_dir` 变成一个**可恢复的本地 workspace**。目录布局：

```text
<workspace>/
  workspace.json          # ad-hoc 清单（与 probe.json 同类，不进冻结 schema）
  source.pdf              # INGEST 保留的源 PDF 字节
  physical.json …         # 各阶段 canonical JSON 产物
  probe.json              # 探测 + routing 诊断 + provider 降级（ad-hoc）
  evidence-bundles.json   # 各 provider bundle 的 ad-hoc 持久化
  resources/              # 图像与 figure PDF fragment
  target.pdf              # committed render artifact
  viewer-publication.json # viewer destination and publication hashes
  build/                  # LaTeX 编译产物（target.pdf），非清单产物
  viewer/data/            # viewer revision（沿用既有发布事务）
```

### 阶段与提交协议

阶段枚举：`INGEST → PHYSICAL → EVIDENCE → LAYOUT → SEMANTIC → TRANSLATE → RENDER → INDEX`（`pdf_pipeline.workspace`）。

- 每阶段在 `workspace.json` 记录：status、产物相对路径 + sha256、producer 版本、阶段缓存键 `inputFingerprint`（见下）。
- status 取值 `pending` / `completed` / `degraded`。`degraded`（批次 D）表示「产物可用但运行中发生了已记录的降级」：`stage_completed` 只认 `completed`，因此该阶段**下次运行必然重跑**（失败不进缓存），而记录本身存在，下游阶段照常读到它的产物并继续。未知 status 一律明确报错。
- 提交顺序：产物先写入 `.staging/`，逐文件原子 replace，最后原子重写 `workspace.json`——清单是**唯一提交指针**。
- 恢复：`stage_completed` 为真（COMPLETED + 产物哈希校验通过 + 缓存键与上游记录和阶段配置一致）才跳过；否则重跑该阶段。中断后重启只重跑未完成阶段；半写入目录永远不会被当成成功。
- 源绑定：manifest 的 `sourceFingerprint` 锁定源 PDF；未知 `workspaceVersion` 与外来源 PDF 一律明确报错。可读版本集合是具名常量 `SUPPORTED_WORKSPACE_VERSIONS`（当前 `("0.1.0",)`）；集合外的版本在**任何 `self.*` 赋值之前**被拒绝，因此被拒绝的 workspace 在磁盘与内存里都不被触碰，也不留 `.staging`。批次 E 不写版本转换函数：批次 A–D 写的都是 `"0.1.0"`，清单形状没有变过（批次 C 改的是键材料，批次 D 加的是 status 取值），旧 workspace 因缓存键自然失配而重跑，不需要迁移，写转换器只会是死代码。未来提升 `WORKSPACE_VERSION` 时，要么把旧版本加进该集合并在 `_load_existing` 里加真实迁移步骤，要么保持拒绝。

权威实现：`packages/python/pdf-pipeline/src/pdf_pipeline/workspace.py` 与 `pipeline.py` 的阶段 runner；决策理由见 Agent Note `2026-09-12-m8-batch-a-workspace-stages`。

### 阶段缓存键与失效传播（M8 批次 C，已收口）

缓存键 = producer 版本 + 上游产物 sha256 + 阶段配置（`pipeline.stage_config_inputs`）。`schemaVersion` 与 `pipelineVersion` 是每个阶段的公共项；其余按阶段：

| 输入变化 | 失效阶段 |
| --- | --- |
| **实际使用的** capability registry 字节（内置 `data/capability-registry.toml`，或 `PAPER_CAPABILITY_REGISTRY` / `--registry` 指向的文件；`registry_fingerprint`，sha256） | EVIDENCE、LAYOUT |
| parser dump 字节（按 adapter 的解析规则定位）/ `MINERU_CMD` / `DOCLING_CMD` / `GROBID_URL` | EVIDENCE |
| 翻译配置：target/source locale、provider model、endpoint、terminology 文件字节 | TRANSLATE |
| render profile / policy / LaTeX 模板字节（`template_fingerprint`） | RENDER |
| 阶段代码或 schema 版本（`pipelineVersion` / `schemaVersion`） | 全阶段 |
| 上游产物哈希（既有规则） | 该阶段及其下游 |

- 配置折进同一个 `inputFingerprint` 字段，**不新增清单字段**，`WORKSPACE_VERSION` 保持 `0.1.0`：键材料扩展只让旧 workspace 全阶段重跑一次（安全方向），升版本反而会拒绝既有 workspace，而迁移/拒绝边界属批次 E。
- registry 与 parser dump 用**内容摘要**而非版本常量：它们是手改数据，改了却忘了升版本时仍必须失效。
- parser 配置只有一个入口（`pdf_pipeline.config.load_parser_config`，镜像 `paper_llm.config`）：优先 `--registry` flag，其次 `PAPER_CAPABILITY_REGISTRY`，最后内置 registry。`run_pipeline` 在**构造 workspace 之前**用 `resolve_registry` 单次读取解析出 `(Registry, digest)`：路由用的表与写进缓存键的摘要必须来自同一次读取，否则两次读取之间的编辑会让记录的摘要与产物不符，形成静默缓存命中。覆盖文件**每次实读、不缓存**（操作者可随时编辑）；内置 registry 是进程内不可变的 package data，解析并 `lru_cache` 一次。
- 覆盖路径只是来源，**路径不入键**：同一份内容放在两个路径得到同一摘要；内容相同的内置副本不会引发重跑。
- 覆盖文件不可读或不合法（TOML 解析失败、缺 internal capability、某 capability 重复列 provider）一律抛 `CapabilityRegistryError`，**绝不回退到内置 registry**——静默回退等于静默换了 parser。默认 registry 的 primary 仍是 `mock` / `docling-sim` / `grobid-sim`；换内置 primary 前必须先用覆盖文件跑 `just benchmark` 证明。
- api key、`timeout_s`、`max_retries`、`cache_dir` **不入键**：它们不影响产物语义。
- 三个真实 parser adapter 一律入键，不按 routing 收窄（routing 需要 probe）：过度失效只多跑一次，误命中会静默陈旧。
- 显式局部重跑：`run_pipeline(..., rerun_from=<stage>)`、CLI `--rerun-from <stage>` 在运行前丢弃该阶段及其下游全部记录（`WorkspaceManager.invalidate_from`），上游记录不动。
- 源 PDF 字节变化默认明确报 `WorkspaceSourceMismatchError`；显式 opt-in `accept_source_change=True` / CLI `--accept-source-change` 重绑 `sourceFingerprint` 并丢弃全部阶段记录，整链重跑（盘上旧产物由各阶段重跑覆写自身声明路径）。
- SEMANTIC 提交前清空 `<ws>/resources/`：该阶段的产物集合是「目录内所有文件」，否则换源或换 figure 集合后旧文件会被当成新产物记录。

翻译缓存（`paper_llm.cache.TranslationCache`）行带 `cacheVersion`（`TRANSLATION_CACHE_VERSION`，当前 `"1"`）；该常量同时是**键派生规则版本**，未知/旧版本的行一律忽略、不做迁移。表节点按 cell 缓存，节点级 `cacheKey` 是整表内容/配置摘要而非缓存地址。

权威实现：`pipeline.stage_config_inputs`、`WorkspaceManager`、`paper_llm.cache`；决策理由见 Agent Note `2026-09-14-m8-batch-c-cache-keys-invalidation`。

### evidence 失败隔离与降级（M8 批次 D，已收口）

EVIDENCE 阶段的 provider 是可选 specialist：一个 provider 失败只降级它自己的 capability，绝不打断整链。

- `routing.collect_bundles` 返回 `ProviderCollection(bundles, degradations)`；provider 异常在边界被隔离成一条 `ProviderDegradation`（`provider` / `capabilities` / `substitutes` / `errorType` / `message`，消息截断到 500 字）。
- 顶替只取 registry 的 `Capability.fallback`（不取 challenger），每个名字每轮最多尝试一次，**不递归**；已在本次运行中收集过的 fallback 直接复用而不重跑，`substitutes` 只列真正产出 bundle 的名字；顶替者自身失败会单独记一条 degradation。
- 每条 degradation 产出一条归属该 provider 的 canonical Issue：`severity = ERROR`、`recoverable = true`、`category` 取自该 capability 映射到的**既有** `IssueCategory`（`table.*` → `TABLE_RECOVERY`、`layout.region` → `LAYOUT_REGION`、`formula.*` → `FORMULA_RECOVERY`、`scholarly.metadata` → `SECTION_STRUCTURE`、`scholarly.bibliography` → `CITATION_RESOLUTION`），`fallback` 记 `provider substitution: <names>` 或该 capability 的内建降级描述；id 由文档 id + provider + capability + message 确定性派生。
- `probe.json` 增 `degradations` 数组（无失败时为 `[]`，形状恒定）；`evidence.json` 的 `issues` 汇总成员 bundle 的 issues 加上降级 Issue（无 issue 时**不写该字段**，因此无失败运行的产物字节不变）。
- 这些 Issue 经 `_run_semantic_stage` 折进 `semantic.json` 的 IssueStore（按 id 去重，顺序 = 既有 issues → 语义校验 issues → evidence issues），是它们到达 viewer 问题列表、`metrics.quality_report` 与 benchmark ERROR 计数的唯一通道。
- 内建基线保证「降级仍可用」：layout region 由几何分带独立产生（不依赖 provider），TABLE 退化为一行一线的单列 fallback（`confidence.reason == "table fallback: line rows"`），scholarly metadata 退化为 front-matter 启发式。
- EVIDENCE 以 `degraded` 提交：产物照常发布、下游继续，但下次运行重跑该阶段（失败不进缓存）；重跑产物字节相同则下游仍被跳过。**所有 routed provider 全失败**（零 bundle）才是真失败，由 `_execute_stage` 归因到 EVIDENCE。
- `ROUTING_VERSION` / `PIPELINE_VERSION` 因此升到 `0.2.0`：前者是 EVIDENCE 缓存键的一部分，后者是所有阶段的公共键项（折入逻辑变了，既有 workspace 整链重跑一次）。

权威实现：`pdf_pipeline.routing`、`pdf_pipeline.evidence.normalize`、`pdf_pipeline.pipeline` 的 EVIDENCE/SEMANTIC runner、`WorkspaceManager.commit_stage(degraded=...)`；决策理由见 Agent Note `2026-09-15-m8-batch-d-specialist-isolation`。

### 当前边界

- `workspace.json` 是 ad-hoc 文件，schema 变更不走 `just schema` 冻结流程。
- viewer revision 发布沿用 `_publish_viewer_revision` 事务，不在清单内逐文件追踪。
- 源 PDF 变化只支持「报错」或「整链重绑」两种模式，不做按阶段合并（Project 分组属后续批次）。
- 不写 workspace 版本转换函数：可读集合外的版本一律拒绝，当前集合只有写入版本 `("0.1.0",)`。
- `apps/api` 与 `apps/worker` 不加 registry 参数：两条路径最终都经 `run_pipeline` / `rerender_workspace` 的默认值读 env，操作者给 worker 进程设 `PAPER_CAPABILITY_REGISTRY` 即同时生效。

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

Issue 形状必须能通过 `document_model.generated.schema_models.Issue` 校验（含 `id`、`producer`、`message`、`affectedIds`）。job 级 Issue **只存 job 记录**，记录的是「哪个阶段整体失败」；文档内 Issue（含批次 D 的 provider 降级）由 EVIDENCE/SEMANTIC 阶段写入 `semantic.json`，见上。

权威实现：`packages/python/pdf-pipeline/src/pdf_pipeline/jobs.py` 与 `pipeline.py` 的 `_execute_stage`；HTTP 契约见 [HTTP API](api.md)；决策理由见 Agent Note `2026-09-14-m8-batch-b-job-orchestration`。

## 仍未决

持久对象存储、多机共享、数据集托管。未来的外部数据集系统需要 testing 或 architecture Agent Note。

保持 Git 历史精简。不要提交大型 PDF 语料。

## 审查修复

恢复时比较当前阶段生产者版本，并读取根目录已提交的 `target.pdf`；`build/` 可删除。INDEX 用发布回执记录 viewer 目标目录、manifest、稳定别名与当前 revision 的哈希，输出缺失或变化时重新发布。局部重译在既有回滚事务中同时发布翻译/渲染阶段记录与根目录目标 PDF，使 INDEX 失效；下一次运行保留新译文。清单写入失败会还原内存阶段记录。理由见 [批次 A 审查修复](../../.agents/notes/implemented/bug-fix/2026-09-12-m8-batch-a-review-repairs.md)。
