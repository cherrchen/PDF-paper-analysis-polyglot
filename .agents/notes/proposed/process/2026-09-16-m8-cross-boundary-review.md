# Agent Note: M8 跨边界验收补充提案

Status: proposed

[中文](./2026-09-16-m8-cross-boundary-review.md) | [English](./2026-09-16-m8-cross-boundary-review.en.md)

## 问题

对 M8 A–F（`750e14d..7f8ce7e`）的审查发现，单批次成功路径与串行产品验收尚未覆盖组合后的共享状态。[批次 B](../../implemented/architecture/2026-09-14-m8-batch-b-job-orchestration.md) 的 workspace 锁不覆盖共享 Viewer 发布目录；[批次 F](../../implemented/architecture/2026-09-16-m8-batch-f-local-e2e.md) 的导入切换未覆盖新文档的局部重译。

2026-09-16 临时确定性交错探针复现：同 workspace 的排队任务连续 20 次认领失败增加 20 个打开的文件描述符；retry 发布 queued 记录后若 worker 立即认领，retry 的清理会删除 running 记录；两个 workspace 向同一目录发布时，后一个发布者的修订清理可删除前一个尚未提交的修订，最终 manifest 指向不存在的目录。这些探针验证实现路径，尚未成为仓库回归测试。

## 提案

后续修复按共享资源补充验收：Job 状态迁移、workspace 写入、Viewer 发布分别列出所有写入入口及锁边界；针对每个边界增加确定性交错测试，保留现有真实 LaTeX 与浏览器成功路径。增加导入第二份文档后的局部重译与阅读器换页失败验收。

## 考虑过的替代方案

- 只增加串行端到端测试：无法稳定命中记录迁移及发布清理的竞态窗口。
- 仅增加随机压力测试：可辅助发现问题，但不适合作为这些已知交错的唯一回归证据。
- 将既有落地 note 改写为未完成：会丢失历史；本提案补充验收要求，保留原始决策。

## 验收标准

- 锁竞争与异常路径不会泄漏文件描述符；重试、认领、查询交错不丢失任务记录。
- 两个 workspace 共用 Viewer 目录时，每个可见 manifest 均引用完整存在的 revision；失败回滚不覆盖其他发布者的成功结果。
- Job 与重译访问同一 workspace 时使用一致的跨进程互斥协议。
- 导入第二份文档后，局部重译操作该文档的 workspace；首屏渲染失败可恢复原阅读器状态。
- 修复经相关 `just` 检查，并区分本地检查结果、远端 CI 与真实 parser 工具验证。

## 风险

锁范围过大会串行化不同文档的计算；应仅在确有共享写入的范围内互斥。本提案未实现修复，亦未改变 M8 的真实 parser 准入边界。

P1 已由[独立修复 note](../../implemented/bug-fix/2026-09-16-m8-p1-concurrency-and-binding.md) 落地；长期验收流程要求仍保留。

P2 首屏事务也已由[独立修复 note](../../implemented/bug-fix/2026-09-16-m8-p2-reader-load.md) 落地；本提案的长期验收流程要求仍待采纳。
