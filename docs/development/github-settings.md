# GitHub 设置

[中文](./github-settings.md) | [English](./github-settings.en.md)

以下 `main` 规则是必需的。本文不声称 bootstrap 已经应用它们。

- 要求 pull request
- 要求状态检查 `CI / gate`
- 要求会话全部解决
- 禁止 force push
- 禁止删除分支
- 要求线性历史（squash merge）

禁止直接推送到 `main`。单一维护者时，批准人数可以为零。

远程存在后，在 GitHub Settings → Rulesets（或经典 branch protection）中应用。
