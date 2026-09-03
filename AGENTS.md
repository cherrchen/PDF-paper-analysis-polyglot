# Agent 站立规则

[中文](./AGENTS.md) | [English](./AGENTS.en.md)

每轮会话的短规则。细节在所链的责任文档中。

## 使命

构建可维护的 PDF 论文分析系统：摄入 PDF、恢复结构、翻译、重建，并通过 LaTeX / LuaLaTeX 渲染。

## 规范命令

以 `just` 作为仓库命令界面。Git hooks、CI、文档与 Agent 都调用同一套 recipe。

见 `justfile`。不要在 GitHub Actions、`package.json` 或本文件中复制命令逻辑。

## 仓库地图

应用：`apps/`。可复用 Python：`packages/python/`。可复用 TypeScript：`packages/typescript/`。Rust：`crates/`。契约：`schemas/`。LaTeX 模板：`templates/latex/`。测试：`tests/`。决策：`.agents/notes/`。Skill：`.agents/skills/`。

不要把可复用业务逻辑散落到各应用里。

## 架构

架构变更前先读 `docs/architecture/` 的当前态文档。持久文档描述当前事实。历史属于 Agent Note。

跨语言契约放在 `schemas/`。不要在 Python、TypeScript 或 Rust 中各自维护权威 SemanticDocument 模型。

## 生成代码

生成代码只有一个真源、一个确定性生成器，禁止手改，并由 CI 做新鲜度检查（`just generate-check`）。

## 测试

禁止仅为让测试通过而更新 golden。遵循 [`docs/testing/golden.md`](docs/testing/golden.md) 与 [`.agents/skills/pdf-regression/SKILL.md`](.agents/skills/pdf-regression/SKILL.md)。

## LaTeX

LaTeX / LuaLaTeX 是初始规范渲染后端。未经 Agent Note，不要引入 Typst 或通用多渲染器架构。不要把生成的 LaTeX 当成语义真源。

## 文档

一事一处。README、`docs/` 与 Agent Note 以中文为主，英文伴侣为 `*.en.md`。遵循 [`docs/development/bilingual.md`](docs/development/bilingual.md)。当前态文档与代码一并更新。

## Agent Note

凡非平凡的行为、架构、契约、流程或测试变更，必须新增或更新 Agent Note。先检索现行 note。不要悄悄改写已落地的决策。归档 note 只是历史，不再具权威。

## 安全

永不提交凭据。遵循 `SECURITY.md`。

## PR

使用 Conventional Commits。填完 [`.github/PULL_REQUEST_TEMPLATE.md`](.github/PULL_REQUEST_TEMPLATE.md)。完成前跑相关 `just` 检查。

## 子树说明

- [`docs/AGENTS.md`](docs/AGENTS.md)
- [`packages/python/AGENTS.md`](packages/python/AGENTS.md)
- [`packages/typescript/AGENTS.md`](packages/typescript/AGENTS.md)
- [`crates/AGENTS.md`](crates/AGENTS.md)
- [`schemas/AGENTS.md`](schemas/AGENTS.md)
- [`templates/latex/AGENTS.md`](templates/latex/AGENTS.md)
- [`tests/AGENTS.md`](tests/AGENTS.md)
- [`.agents/notes/AGENTS.md`](.agents/notes/AGENTS.md)
