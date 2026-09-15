# Agent Note: M8 批次 D specialist 失败隔离与显式降级

Status: implemented

[中文](./2026-09-15-m8-batch-d-specialist-isolation.md) | [English](./2026-09-15-m8-batch-d-specialist-isolation.en.md)

## 问题

M7 的 planner 会把 table-dense 文档路由到 Docling 类 specialist（[2026-09-12-m7-parser-ensemble](./2026-09-12-m7-parser-ensemble.md)）。但 `routing.collect_bundles` 顺序调用每个 routed provider，**任一异常直接冒泡**：`_execute_stage` 把它包成 `StageExecutionError`，Job 判为失败，整篇文档连同已成功的 layout/semantic 一起丢失。一个可选 specialist 的缺席让整条链停摆，而架构上它只拥有一个 capability。

第二处缺口在 `evidence/normalize.py`：`merge_evidence_bundles` 只合并 candidates 与 provenance，**静默丢弃成员 bundle 的 `issues`**。因此即使 provider 自己报告了失败，也没有任何路径能让它到达 `semantic.json`、viewer 的问题列表、`metrics.quality_report` 或 benchmark 的 ERROR 计数——失败不可观测。

批次 D 的验收（[`docs/development/m8.md`](../../../../docs/development/m8.md)）：Docling 类失败 → TABLE 行 fallback + Issue，文档其余节点继续，不得把整篇标成 parse failed。同时失败不得进入缓存（批次 C 的缓存键语义）。

## 决策

1. **provider 边界吞异常，`collect_bundles` 返回 `ProviderCollection(bundles, degradations)`**，`ROUTING_VERSION` → `0.2.0`。每个 routed provider 一次尝试包在 `_attempt` 里；`Exception` 被转成 `ProviderDegradation(provider, capabilities, substitutes, errorType, message)` 而不是继续冒泡。`message` 形如 `"<ErrorType>: <str(error)>"`，截断到 `MAX_ERROR_MESSAGE_CHARS = 500`（诊断信息不是 payload）。
2. **顶替只取 registry 的 `Capability.fallback`，不取 challenger；每个名字每轮最多尝试一次；不递归**。`substitutes` 只列**真正产出 bundle** 的名字：若该 fallback 已在本轮为别的 capability 收集过（例如 `table.structure.fallback = mock` 而 `mock` 就是 layout primary），直接复用，**不重跑**。fallback 自身失败时单独记一条 degradation，排在它所顶替的那条之后（只降一级，不做链式顶替）。
3. **同一 provider 被路由到多组 capability 时不静默算成功**：`_attempt` 缓存失败对象，第二次判定复用同一条失败记录并各自产出 degradation，而不是因为「名字已尝试过」就当作成功。
4. **Issue 归属失败 provider**：`severity` 恒为 `ERROR`（真实 provider 失败是缺陷，WARNING 会掩盖）、`recoverable = true`、`affectedIds = []`、`id = stable_uuid(document_id, "issue", provider, capabilities, message)`（确定性，重跑不产生重复 Issue）。`category` 由 capability 映射到**既有** `IssueCategory`（`_CAPABILITY_ISSUE_CATEGORY`：layout.region→LAYOUT_REGION、table.*→TABLE_RECOVERY、formula.*→FORMULA_RECOVERY、scholarly.metadata→SECTION_STRUCTURE、scholarly.bibliography→CITATION_RESOLUTION），无命中回落 `LAYOUT_REGION`——不新增 schema 枚举。`fallback` 有顶替者时写 `"provider substitution: <names>"`，否则写 capability 的内建降级描述（`_CAPABILITY_FALLBACK_DESCRIPTION`，如 table 的 `"table line-row fallback"`、scholarly.metadata 的 `"front-matter heuristics"`）。`fallback` 属 `Issue.__non_nullable_optional_fields__`，绝不明传 `None`。
5. **`probe.json` 增 `degradations` 字段**（`[d.to_json() for d in degradations]`，无失败时为 `[]`）。形状恒定，ad-hoc 文件不进冻结 schema；`category`/`errorType`/`message` 与 Issue 同源。
6. **`StageStatus.DEGRADED` 表示「产物可用但已降级」**：`commit_stage(..., degraded=True)` 写 `"status": "degraded"`，`stage_completed` 只认 COMPLETED，因此**下次运行重跑该阶段**（失败不进缓存），而记录本身存在，`_upstream_artifacts` 照常读到它的产物哈希，LAYOUT 及下游继续提交。**不升 `WORKSPACE_VERSION`**：旧 workspace 仍可读（批次 C 的键材料扩展本来就会让它们重跑一次），降级是新写入的状态；迁移/拒绝边界仍归批次 E。
7. **`merge_evidence_bundles(bundles, *, issues=())`**：结果 issues = 各成员 bundle 自己的 issues + 传入的 issues。**为空时不写 `issues` 字段**（`EvidenceBundle.__non_nullable_optional_fields__` 含 `issues`，且这样无失败运行的产物逐字节不变，golden 不动）。空输入仍抛 `ValueError`。
8. **evidence issues 折进 `semantic.json` 的 IssueStore 是唯一通道**：`_run_semantic_stage` 在 `validate_semantic_recovery` 折入之后追加 evidence issues，按 `id` 去重，顺序 = 既有 issues → recovery issues → evidence issues。`PIPELINE_VERSION` → `0.2.0`：`pipelineVersion` 是所有阶段缓存键的公共项，折入逻辑变了必须让既有 workspace 整链重跑一次。
9. **零 bundle 是真失败**：`_run_evidence_stage` 在 `collection.bundles` 为空时抛 `RuntimeError`（消息列出每条 degradation 的 provider + 错误），由 `_execute_stage` 归因到 `EVIDENCE`。没有任何 evidence authority 时不该伪装成「降级成功」。
10. **`EvidenceProvider.collect` 的契约写进 docstring**：可以抛；router 隔离 provider 失败并为丢失的 capability 顶替 registry fallback。

不改动 `fusion.py`、`layout.py`、`sem_tables.py`：几何 region 由 `layout.py` 的 `page_structure` 分组独立产生（不依赖 provider），TABLE 行 fallback 与 `confidence.reason == "table fallback: line rows"` 在 M4 就已存在，本批次只是让「specialist 失败」真正走到那条路径。也不改 `schemas/` 与生成代码。

## 考虑过的替代方案

- **静默跳过失败 provider，不记 Issue**：正是本次要修的缺口——失败必须可观测，否则 viewer/benchmark 永远看不见降级。
- **fallback 递归解析（fallback 的 fallback）**：一条失败会让顶替链无限延伸，且 `substitutes` 语义变模糊（谁真正产出了 bundle？）。只降一级、名字去重是可预测的。
- **取 challenger 顶替**：challenger 是「同一 capability 的次优证据源」，不是「主 provider 死后的补位」；registry 已有 fallback 槽表达后者。
- **新增 IssueCategory 成员**（如 `EVIDENCE_PROVIDER`）：需要改冻结 schema + 重新生成绑定；已有分类足以表达受影响能力。
- **provider 失败记 WARNING**：掩盖真实缺陷；sim registry 永不失败，真实 adapter 失败就是 ERROR。
- **升 `WORKSPACE_VERSION` 表达「出现了新状态值」**：会直接拒绝既有 workspace，而迁移策略属批次 E；旧代码读到 `"status": "degraded"` 会显式报 `unknown stage status`，是「明确拒绝」而非静默误用。
- **把 provider 失败只写进 Job 记录（批次 B 的做法）**：`semantic.json` 必须自带它，否则 viewer、quality report、benchmark 三个消费者都要各自知道 job 记的是什么。
- **`merge_evidence_bundles` 总是写 `issues=[]`**：会让无失败运行也改变产物字节，golden 与 benchmark 基线无谓抖动。
- **degraded 阶段仍按 COMPLETED 记账（只记 Issue）**：失败会被缓存成结果，下次运行不再重试。
- **把 `_attempt` 已尝试且失败当作成功**：同一 provider 被路由到两组 capability 时，第二组会既无 bundle 也无 degradation——静默失败，与本次目标相反。

## 后果

- `pdf_pipeline/routing.py`：`collect_bundles(plan, physical, registry=None) -> ProviderCollection`（不再是 `list`）；新增 `ProviderDegradation`、`ProviderCollection`、`issue_category_for_capability`、`fallback_description_for_capability`、`MAX_ERROR_MESSAGE_CHARS`、两个 capability 映射表；`ROUTING_VERSION` `0.1.0` → `0.2.0`（EVIDENCE 缓存键的一部分）；`document_model.generated` 从 `TYPE_CHECKING` 提升为运行时导入（`to_issue` 要构造 `Issue`）。
- `pdf_pipeline/evidence/normalize.py`：`merge_evidence_bundles` 增 keyword-only `issues`。
- `pdf_pipeline/workspace.py`：`StageStatus.DEGRADED`；`StageRecord.from_json` 接受该值；`make_stage_record` / `commit_stage` 增 `degraded: bool = False`。
- `pdf_pipeline/pipeline.py`：`PIPELINE_VERSION` `0.1.0` → `0.2.0`；`_run_evidence_stage` 用 `ProviderCollection`、写 `probe.json.degradations`、零 bundle 抛错；`_run_semantic_stage` 折入 evidence issues。
- `tests/benchmark/run_benchmark.py`：改用 `ProviderCollection`（sim registry 无失败 → 报告与 baseline 逐字节不变）。
- 调用点已全部迁移：`pipeline`、`run_benchmark`、`test_routing`、`test_semantic`；无兼容垫片。
- 既有 workspace 首次运行会因 `pipelineVersion` 变化整链重跑一次（批次 C 的预期），此后照常。
- 验证：`test_routing.py` 12 项、`test_workspace.py` 26 项、`test_semantic.py` 24 项、新增 `test_specialist_isolation.py` 3 项全绿；`just test-python` 523 passed；`just test-golden`（`tests/golden/smoke/semantic.json` 未变）；`just benchmark` 退出 0、报告 unchanged、baseline 未改；`just check-fast` 通过。端到端可观察结果：table-heavy + Docling 缺失 → `semantic.json` 的 TABLE 为单列 9 行 fallback（`reason == "table fallback: line rows"`）、一条 producer `docling` 的 `TABLE_RECOVERY` ERROR Issue（`fallback == "provider substitution: mock"`）、`probe.json.degradations[0].substitutes == ["mock"]`、`workspace.json` 中 evidence 为 `degraded` 而其余 `completed`；重跑时 EVIDENCE 运行 1 次、LAYOUT 0 次。paper-anatomy + GROBID 缺失 → SECTION/PARAGRAPH 节点仍在，一条 `SECTION_STRUCTURE` Issue（`fallback == "front-matter heuristics"`）。全部 routed provider 失败 → `StageExecutionError`（EVIDENCE），不写 `semantic.json`。
