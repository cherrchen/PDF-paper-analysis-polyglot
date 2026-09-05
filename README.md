# PDF 论文分析

[中文](./README.md) | [English](./README.en.md)

面向 PDF 论文分析、文档理解、翻译、结构重建与 PDF 渲染的多语言单仓。

**状态：** M1 核心契约、M2 Walking Skeleton 与 M3 Layout Recovery Engine 已完成。端到端管线、双向 Viewer 与版面恢复已通过重新验收。当前进度以[开发路线图](docs/development/roadmap.md)为准。

## 渲染

当前渲染后端是 **LaTeX / LuaLaTeX**：

```text
SemanticDocument
      +
TranslationLayer
      ↓
RenderComposer
      ↓
RenderDocument
      ↓
LaTeX Backend
      ↓
LuaLaTeX
      ↓
PDF
```

LaTeX 是渲染表示。SemanticDocument 仍是语义真源，翻译内容和排版决策分别属于 TranslationLayer 与 RenderDocument。

## 仓库地图

| 路径 | 职责 |
| --- | --- |
| `apps/` | 运行时入口（`web`、`api`、`worker`） |
| `packages/python/` | 可复用 Python |
| `packages/typescript/` | 可复用 TypeScript |
| `crates/` | 性能关键 Rust |
| `schemas/` | 跨语言契约真源 |
| `templates/latex/` | 一等 LaTeX 模板 |
| `tex/` | TeX Live 宏包清单与 latexmk 配置 |
| `tests/` | 夹具、golden、集成、端到端 |
| `docs/` | 当前态文档 |
| `.agents/` | Agent Note 与 Skill |

可复用逻辑不属于应用目录。

## 快速开始

```bash
mise install
just setup
just doctor
just check
```

必须安装 LaTeX（TeX Live 2026 / MacTeX，LuaLaTeX，latexmk）。`just setup` 不会跳过它。

## 规范命令

使用 `just`。不要把 `uv`、`pnpm`、`cargo` 或 `latexmk` 当成主开发界面。

| 命令 | 含义 |
| --- | --- |
| `just setup` | 安装工作区与 hooks |
| `just doctor` | 校验工具链 |
| `just check-fast` | 推送前校验 |
| `just check` | 开发者完整校验 |
| `just ci` | 穷尽检查 |

完整界面见 `just --list`。

## 文档

- 架构：[`docs/architecture/overview.md`](docs/architecture/overview.md)
- 开发总路线：[`docs/development/roadmap.md`](docs/development/roadmap.md)
- 环境：[`docs/development/setup.md`](docs/development/setup.md)
- 双语文档：[`docs/development/bilingual.md`](docs/development/bilingual.md)
- 测试：[`docs/testing/overview.md`](docs/testing/overview.md)
- Agent 站立规则：[`AGENTS.md`](AGENTS.md)

## 许可

MIT 许可证 **外加非商用附加条款**。允许个人、学术、教育与研究使用。未经另行书面许可，禁止商用。见 [`LICENSE`](LICENSE)。

这是源码可得（source-available），不是未经修改的 OSI 认可 MIT。
