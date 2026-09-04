# 工作流

[中文](./workflow.md) | [English](./workflow.en.md)

在 `main` 上做主干开发。功能分支：`feat/*`、`fix/*`、`refactor/*`、`docs/*`、`ci/*`、`chore/*`。没有 `develop` 分支。

`main` 保持可发布。使用 squash 合并。PR 标题遵循 Conventional Commits。

仓库任务一律用 `just`。Lefthook 在 commit 时跑暂存检查（含双语文档），在 push 时跑 `just check-fast`。

命令归属：[`.agents/notes/implemented/process/2026-09-03-canonical-repository-commands.md`](../../.agents/notes/implemented/process/2026-09-03-canonical-repository-commands.md)。

人文档配对：[`bilingual.md`](bilingual.md)。开发总路线：[`roadmap.md`](roadmap.md)。
