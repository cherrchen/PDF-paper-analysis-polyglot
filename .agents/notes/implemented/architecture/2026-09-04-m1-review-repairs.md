# Agent Note: M1 契约审查修复

Status: implemented

[中文](./2026-09-04-m1-review-repairs.md) | [English](./2026-09-04-m1-review-repairs.en.md)

## 问题

对 `6948642..HEAD` 的 M1 审查认定 Exit Gate 未通过：Python 生成模型比 JSON Schema 更松；fixture ID 碰撞；所谓 N→N / 跨页映射未真正覆盖；bundle 引用校验漏报；`just generate-check` 与 Vale 门禁失败；Roadmap 中的 `StructureCandidate`、`LayoutGroup`、`RichText` 未落地或未记录。

## 决策

在进入 M2 之前先补齐 M1 契约，而不是把缺口推迟：

1. Pydantic 生成器把 JSON Schema 的「可省略」与「可 null」分开，并生成 `pattern`、`maxItems` 以及可选字段上的数值约束。TypeScript 运行时校验器同步覆盖 `maxItems` / `maxLength` / `exclusiveMaximum`。
2. Fixture ID 把变化的序号放在 26 字符的尾部，生成时检测碰撞。
3. Mapping fixture 用独立的跨页 region/span 覆盖跨页 N→1，用共享多 fragment anchor 覆盖连通的 N→N。
4. `validate_bundle_references` 校验 `rootId`、relation 端点、重复 ID，以及 parent/children 互指。
5. `just generate` 在写出 Pydantic 后运行 Ruff format，使 `just generate-check` 与 `just fmt` 一致。
6. Schema 补齐 `StructureCandidate`、`LayoutGroup`，并以 `RichText` 为规范名、`TextNodeContent` 为别名。
7. Phase 1.2「同一 PDF 多次解析」在 M1 明确为 JSON 反序列化稳定性；PDF 字节重复解析属于 M2.1。

与 [M1 核心文档契约落地](./2026-09-04-m1-core-document-contracts.md) 交叉：原决策仍成立，本 note 记录审查后补齐的等价性与完整性约束。

## 考虑过的替代方案

- 把 M1 标为未完成并冻结现状：会把非法 ID、重复 identity 和假 N→N 带进 M2。
- 仅更新 Roadmap 声明缩减范围、不补 schema：与已冻结的 Document Architecture v0.1 用词不一致。
- 手改生成的 Pydantic 文件：违背「禁止手改生成物」。

## 后果

- Python / JSON Schema / TypeScript 对非法 ID、`title=null`、5 点 Quad、负 `byteLength` 的拒绝行为对齐。
- Physical fixture 对象 ID 唯一；跨页 paragraph 的 physical span 分属两页。
- CI docs job 的 `just generate-check` 与 `just docs`（含 Vale）在本机可复现通过。
- 下一阶段 M2 可以依赖这套已补齐的五层契约，不必先绕过生成器或 fixture 缺陷。
