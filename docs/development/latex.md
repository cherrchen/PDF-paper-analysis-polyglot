# LaTeX

[中文](./latex.md) | [English](./latex.en.md)

## 当前策略

| 项 | 值 |
| --- | --- |
| 发行版 | TeX Live 2026 |
| 默认引擎 | LuaLaTeX |
| 驱动 | 经 `tex/latexmkrc` 的 latexmk |
| 宏包集 | `tex/packages.txt`（含 `luatexja`、`fandol`、`caption`、`multirow`） |
| 模板 | `templates/latex/` |

XeLaTeX 仅在有文档化的兼容需求时允许。pdfLaTeX 不是多语言渲染器。

## 本地安装

macOS：MacTeX 2026（`brew install --cask mactex-no-gui`）或完整 TeX Live 2026 树。

Linux：从 TUG 安装 TeX Live 2026，再用 `tlmgr` 对齐 `tex/packages.txt`。

`just doctor` 必须看到 `lualatex`、`latexmk`、`chktex` 与 `latexindent`。缺少 LaTeX 是硬失败。

## CI

CI 安装钉死的 TeX Live 2026 以及 `tex/packages.txt`。本地不需要 Docker。

## 警告策略

致命错误使构建失败（`-halt-on-error`）。缺少必需宏包使构建失败。期望的 PDF 缺失使构建失败。

一等模板不得堆积无法解释的警告。第三方学术模板可能发出无害排版警告；不要全局关闭 ChkTeX 来掩盖它们。

## 调试

1. 阅读源文件旁 `build/` 目录下的 `.log`。
2. 再跑 `just latex-smoke`。
3. 修模板或未声明宏包。不要靠削弱仓库检查来消音。

## TeX Live 升级

提高文档中的年份、更新 CI `texlive_version`、刷新 `tex/packages.txt`，并在 Agent Note 中记录。Renovate 不管 TeX 宏包。
