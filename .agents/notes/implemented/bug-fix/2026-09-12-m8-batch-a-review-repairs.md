# Agent Note: M8 批次 A 审查修复

Status: implemented

[中文](./2026-09-12-m8-batch-a-review-repairs.md) | [English](./2026-09-12-m8-batch-a-review-repairs.en.md)

## 问题

批次 A 恢复读取未跟踪的 build PDF，生产者版本只与自身比较，INDEX 跳过缺失或新目标的 viewer。局部重译未同步清单与根目录 PDF，恢复会覆盖重译结果；清单写入异常时内存记录提前完成。非法 status 类型也会泄漏 TypeError。

## 决策

补足 [批次 A 契约](../architecture/2026-09-12-m8-batch-a-workspace-stages.md)：恢复使用已提交 PDF、比较当前生产者版本；INDEX 保存发布回执并检查目标与产物哈希；局部重译将新阶段记录与根目录 PDF 纳入既有回滚事务，并失效 INDEX。清单写入失败还原内存状态，非法 status 和 UTF-8 统一报告 WorkspaceError。当前态见 [存储](../../../../docs/architecture/storage.md)。配置缓存仍属批次 C。

## 考虑过的替代方案

- 每次重新编译与翻译：丢失阶段恢复价值，也覆盖用户重译。
- 每次发布 viewer：产生无必要的 revision，改用哈希回执。
- 重译后单独写清单：失败后清单与产物可能不一致，采用已有发布回滚事务。

## 后果

增加恢复、版本升级、viewer 修复、重译保留和清单失败回归测试。局部重译后的首次恢复重建 INDEX。无需修改冻结 schema 或 golden。

产物路径必须保持在 workspace 内，且不能覆盖清单或 staging 保留路径；加载清单与提交入口均校验。
