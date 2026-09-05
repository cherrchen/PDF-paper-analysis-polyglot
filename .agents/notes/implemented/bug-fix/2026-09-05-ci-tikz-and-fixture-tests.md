# Agent Note: CI 夹具 PDF 与 TikZ 宏包

Status: implemented

[中文](./2026-09-05-ci-tikz-and-fixture-tests.md) | [English](./2026-09-05-ci-tikz-and-fixture-tests.en.md)

## 问题

`c83086a` 的 `CI / gate` 在 Python 与 LaTeX 作业失败。Python job 没有 TeX，不编译 `tests/fixtures/source/latex/build/` 下的 PDF；`test_render.py` 与 golden 测试直接打开这些文件，导致 13 个 `FileNotFoundError`。其余夹具测试 skip 之后，覆盖率只有约 66%，低于 `fail_under = 80`。LaTeX job 编译 `tikz-vector.tex` 时缺少 `tikz.sty`：`tex/packages.txt` 未声明 `pgf` 及其依赖。

## 决策

1. 在 `tex/packages.txt` 加入 `pgf`、`xcolor`、`ms`。`tikz-vector` 需要 TikZ；CI 的精简 TeX Live 不会安装未列出的宏包。
2. 所有依赖夹具 PDF 的测试在文件缺失时 `pytest.skip`，并提示运行 `just latex-smoke`。本机未先编译时不应崩溃。
3. Python job 安装与 LaTeX job 相同的 TeX Live 2026 与 `tex/packages.txt`，在 `just test-python` 之前运行 `just latex-smoke`。这样覆盖率门禁与 11 个 Tier-1 全链测试在 clean checkout 上真正执行，而不把 `just test-python` 拆成另一套 CI 命令。

本 note 补充 [首次 CI 闸门修复](../process/2026-09-03-ci-first-run-fixes.md) 与 [Git 与 CI 治理](../process/2026-09-03-git-and-ci-governance.md)，不改变按生态拆分作业或 LuaLaTeX 后端。

## 考虑过的替代方案

- 把编译后的 PDF 提交进仓库：违反夹具「源文件入库、PDF 由 latex-smoke 生成」的约定，也会膨胀 Git 历史。
- 只 skip、不在 Python job 编译夹具：覆盖率约 66%，`just test-python` 仍然失败。
- 把覆盖率门禁降到 warning 或拆成另一条 CI 专用命令：会让 GitHub Actions 与 `justfile` 漂移。
- 只在 LaTeX job 跑 pytest、Python job 关掉 `fail_under`：夹具回归不再由 Python 作业拥有，且本地 `just test-python` 在未编译时也会因覆盖率失败。

## 后果

Clean checkout 的 Python job 先编译夹具再测。缺少 PDF 时测试 skip，而不是崩溃。新增需要 TikZ 或其它 TeX 宏包的夹具时，必须同步更新 `tex/packages.txt`。Python job 与 LaTeX job 都安装 TeX；共享的 TeX Live 缓存使第二次安装便宜。
