# Agent Note: M8 批次 A 本地 workspace 与阶段状态契约

Status: implemented

[中文](./2026-09-12-m8-batch-a-workspace-stages.md) | [English](./2026-09-12-m8-batch-a-workspace-stages.en.md)

## 问题

[M8 准入收口](../process/2026-09-12-m8-admission-closeout.md) 之后批次 A（本地 workspace 与阶段状态）开工时，`run_pipeline` 是一次性的单体函数：产物在全部阶段结束后才落盘，进程中断即丢失全部进度；没有阶段枚举、阶段状态、生产者版本或输入指纹的记录；`docs/architecture/storage.md` 仍写着「有意未决」。批次 B 的任务编排、批次 C 的缓存键、批次 E 的版本迁移都需要一个先行的阶段状态契约。

## 决策

1. **新增 `pdf_pipeline.workspace` 清单模块**（不放 `apps/`）。`workspace.json` 是 ad-hoc 清单（与 `probe.json` 同类），**不进冻结 schema**、不走 `just schema` 流程；`workspaceVersion` 当前为 `0.1.0`。
2. **阶段枚举** `INGEST → PHYSICAL → EVIDENCE → LAYOUT → SEMANTIC → TRANSLATE → RENDER → INDEX`（`Stage` / `STAGE_ORDER` / `STAGE_DEPENDENCIES`）。每阶段记录：status、产物相对路径 + sha256、producer 版本（复用各模块既有版本常量；RENDER/INDEX 新增阶段版本）、输入指纹（生产者版本 + 上游记录产物哈希）。
3. **目录级原子提交**：产物先写 `.staging/<stage>-<token>/`，逐文件原子 replace，最后原子重写 `workspace.json`——清单是唯一提交指针。失败或中断后清单不变，下一轮视该阶段未完成并重跑；半写入目录永远不被当成成功。
4. **跳过条件**：COMPLETED + 全部产物哈希校验通过 + 记录的输入指纹与当前上游记录一致。上游重提交（产物哈希变化）即传递性失效下游。
5. **figure 资源绑定移入 SEMANTIC 阶段**：`semantic.json` 从此只有 SEMANTIC 一个所有者，落盘内容仍是 figure 绑定后的版本（与历史 on-disk 契约一致）。翻译只处理文本节点，绑定不影响任何翻译产物，因此全量跑产物字节不变。
6. **EVIDENCE 阶段持久化各 provider bundle**（ad-hoc `evidence-bundles.json`），使恢复的 LAYOUT 阶段不必重调 provider；`probe.json` 落盘时机提前到本阶段，内容不变。
7. **严格拒绝而非迁移**：未知 `workspaceVersion`、无法解析的清单、外来源 PDF（`sourceFingerprint` 不匹配）均明确报错。版本迁移属批次 E。

当前态文档：[`docs/architecture/storage.md`](../../../../docs/architecture/storage.md)（已从「有意未决」收口本地 workspace 部分）。

## 考虑过的替代方案

- **RENDER 阶段覆写 `semantic.json`（保持现有执行顺序）**：一个文件两个所有者会破坏按哈希的阶段校验，被绑定移入 SEMANTIC 取代。
- **把 `workspace.json` 建模进冻结 schema**：清单是本地实现细节且将随批次 B/C 演进，冻结流程成本不成比例。
- **恢复时重算 provider bundles（不持久化）**：mock registry 下廉价，但批次 D/E 引入真实 adapter 后是网络/重型调用，违背「只重跑未完成阶段」。
- **COMPLETED 只看清单、不校验产物哈希**：篡改或截断的产物会被当成成功，不满足验收。
- **为每个阶段建独立子目录 + 完成标记**：目录树更深，且与既有 workspace 根级 canonical 文件名契约（`rerender_workspace` 等消费方）冲突。

## 后果

- 中断后重启只重跑未完成阶段；已完成 JSON/PDF 原样保留（`test_pipeline_resume.py` 以阶段计数断言）。
- 批次 B 可按 `Stage` 把 `run_pipeline` 阶段切成可恢复 Job；批次 C 可在 `input_fingerprint` 上扩展配置/代码版本；批次 E 可在 `WorkspaceVersionError` 处接入迁移。
- 翻译配置变化当前**不会**使 TRANSLATE 阶段失效（指纹只含上游产物哈希）；这是批次 C 的已知边界，不是缺陷。
- 清单含每产物 sha256，恢复时代价是重读并哈希上游产物，本地规模可接受。
- 验证：`just lint-python`、`just typecheck-python`、`just test-python`（450 通过，新增 `test_workspace.py` 10 项、`test_pipeline_resume.py` 4 项）。
