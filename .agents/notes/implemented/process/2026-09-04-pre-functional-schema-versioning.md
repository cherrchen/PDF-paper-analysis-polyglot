# Agent Note: 首个功能前的 Schema 版本边界

Status: implemented

[中文](./2026-09-04-pre-functional-schema-versioning.md) | [English](./2026-09-04-pre-functional-schema-versioning.en.md)

## 问题

M1 建立了 `0.1.0` schema 开发基线，但仓库尚未形成可运行的端到端功能。把开发基线等同于已发布的兼容性冻结，会迫使功能形成前的契约修正产生没有真实消费者或迁移对象的版本升级。

## 决策

在首个功能纵切通过 Exit Gate 前，所有 canonical document schema 继续使用 `0.1.0` 作为开发目标。该阶段允许破坏性修正保留版本号，但 canonical schema、fixtures、生成绑定和跨语言测试必须在同一变更中更新。

首个功能纵切通过 Exit Gate，或任何 schema / 生成包提前发布时，兼容性冻结生效；此后的破坏性修改必须遵循版本升级、migration、fixture、兼容性测试和 Agent Note 要求。

本决策限定的是 wire/schema 兼容性边界，不解除 Document Architecture v0.1 作为架构基准的地位。它补充 [M1 核心文档契约落地](../architecture/2026-09-04-m1-core-document-contracts.md) 与 [M1 契约审查修复](../architecture/2026-09-04-m1-review-repairs.md) 中的“冻结”表述。

## 考虑过的替代方案

- 每次开发期破坏性修正都升级版本：没有已发布消费者，版本和迁移只会制造噪声。
- 完全取消版本治理：无法定义功能形成后的兼容性承诺，也无法保护持久化数据。
- 等到首个正式发行版才冻结：端到端功能可能在正式发行前已产生持久化数据和内部调用方，边界过晚。

## 后果

- 当前 `LayoutDocument.groups` 等开发期修正可以继续属于 `0.1.0`，不需要虚构 migration。
- 开发期契约变更仍必须通过 `just schema`、语言检查和 `just generate-check`。
- 首个功能纵切或提前发布会建立明确且可审计的兼容性冻结点。
