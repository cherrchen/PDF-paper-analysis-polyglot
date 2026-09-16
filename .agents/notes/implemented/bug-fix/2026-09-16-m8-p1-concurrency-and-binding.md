# Agent Note: M8 P1 并发一致性与重译绑定修复

Status: implemented

[中文](./2026-09-16-m8-p1-concurrency-and-binding.md) | [English](./2026-09-16-m8-p1-concurrency-and-binding.en.md)

## 问题

[M8 审查](../../proposed/process/2026-09-16-m8-cross-boundary-review.md) 发现五项 P1：共享 Viewer 发布目录互删修订；retry 删除刚被认领的 running 记录；认领失败泄漏描述符；导入后重译仍绑定启动 workspace；Job 与重译未共用 workspace 锁。本 note 补充[批次 B](../architecture/2026-09-14-m8-batch-b-job-orchestration.md) 与[批次 F](../architecture/2026-09-16-m8-batch-f-local-e2e.md) 的并发和绑定契约，不重写历史。

## 决策

1. 新增 `pdf_pipeline.locks`，以规范化资源路径派生跨进程 `flock`，锁文件位于资源父目录 `.paper-pipeline-locks/`，不随 workspace 或修订清理。同线程可重入；锁顺序固定为 workspace → Viewer。
2. `run_pipeline` 与 `rerender_workspace` 在读取产物前获取同一 workspace 锁，覆盖 CLI、worker、API 以及不同 jobs root。Job 的 workspace 锁继续用于队列调度。
3. Viewer 锁覆盖旧 manifest 读取、修订创建、提交、回滚、清理；INDEX 在同一锁内记录发布回执，回执缓存检查也读取锁下快照。
4. retry 在 job 锁内校验并迁移，竞争返回状态冲突。认领锁内重读 queued；未转交 claim 的描述符在 `finally` 释放。执行器失败只释放已取消任务的锁，仍执行的任务由自身释放。
5. manifest 增加服务端生成的绝对 workspace 绑定。浏览器重译传 revision；API 据绑定选文档，解析和最终提交均校验 revision。旧 manifest 无绑定时回退启动 workspace。INDEX producer 升为 `0.2.0`，旧 workspace 只需重新发布绑定。

## 考虑过的替代方案

- API 线程锁不能保护另一个 worker 或 CLI 进程。
- 用 Viewer 锁包围全部计算会无谓串行化不同文档；锁只覆盖共享发布与回执。
- 客户端传 workspace 路径选择目标不能替代服务端修订绑定。
- 清理锁文件可能产生两个不同 inode，使互斥失效。

## 后果

- 新增确定性交错、描述符、跨进程锁、API 绑定与过期发布回归；产品验收增加第二份文档导入后的重译与旧 revision 拒绝。
- 当前态见[存储](../../../../docs/architecture/storage.md)与[API](../../../../docs/architecture/api.md)。
- 保持 POSIX、本地路径式导入、workspace 版本和 canonical schema，不更新 golden。
- P2 首屏渲染失败已由[独立修复 note](2026-09-16-m8-p2-reader-load.md) 覆盖。
