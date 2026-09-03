# Agent Note: 依赖管理策略

Status: implemented

[中文](./2026-09-03-dependency-management-policy.md) | [English](./2026-09-03-dependency-management-policy.en.md)

## 问题

多语言仓库会堆积重叠工具、许可证不兼容的 crate，以及未声明的 TeX 宏包。

## 决策

uv、pnpm 与 Cargo 是仅有的语言依赖管理器。Renovate 更新 npm、Python、Cargo 与 GitHub Actions。不为这些生态配置 Dependabot。`cargo-deny` 强制 Rust 公告、许可证、禁令与来源策略。TeX 宏包列在 `tex/packages.txt`，不通过 Renovate 伪造。重型原生库需要 Agent Note。

## 考虑过的替代方案

- 在 uv 旁边再用 Poetry 或 Pipenv 会分裂 Python 解析。
- 在 pnpm 旁边再用 npm 或 yarn lockfile 会分裂 JavaScript 解析。
- Dependabot 加 Renovate 会重复噪音。

## 后果

未经 process note，禁止再引入与 Ruff、Biome 或 rustfmt 重叠的工具。本仓库的许可证元数据是定制的（MIT 加非商用），不得在注册表中标成未经修改的 MIT。
