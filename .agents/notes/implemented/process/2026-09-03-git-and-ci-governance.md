# Agent Note: Git 与 CI 治理

Status: implemented

[中文](./2026-09-03-git-and-ci-governance.md) | [English](./2026-09-03-git-and-ci-governance.en.md)

## 问题

`main` 必须保持可发布，同时仍允许快速本地迭代。

## 决策

在 `main` 上做主干开发。Squash 合并。Conventional Commits。Lefthook 负责 pre-commit 与 pre-push（`just check-fast`）。GitHub Actions 按生态拆分，并以单一 `CI / gate` 状态汇总。Linux 是穷尽 CI。macOS 与 Windows 是后续可移植性冒烟。分支保护设置已文档化，必须在 GitHub 远程上应用。

## 考虑过的替代方案

- 长期 `develop` 分支会推迟可发布性，而当前并无此需求。
- 一个巨型 workflow 无法维护。
- 每次 pre-commit 都跑完整 E2E 与语料测试会毁掉 hook 延迟。

## 后果

hooks 保持快速。PR CI 覆盖格式、lint、类型、单元测试、文档、schema、LaTeX 冒烟，以及 Python job 在 `just latex-smoke` 与 `just test-python` 之后运行的 `just benchmark` 质量门禁。Python job 安装与 LaTeX job 相同的 TeX Live 宏包集，因为夹具 PDF 不入库，而覆盖率与 benchmark 门禁需要它们。缺少 PDF 时依赖夹具的测试 skip。Nightly 复用同一 `ci-python.yml`（含 benchmark），不再单独重装 TeX 跑第二遍。在真正应用之前，不要默默假设 GitHub ruleset 已经存在。夹具 PDF 与 TikZ 宏包细节见 [CI 夹具与 TikZ 修复](../bug-fix/2026-09-05-ci-tikz-and-fixture-tests.md)。Benchmark 进入 PR CI 见 [M8 准入收口](./2026-09-12-m8-admission-closeout.md)。
