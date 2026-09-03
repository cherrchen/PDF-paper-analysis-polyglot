# Agent Note: 以 LaTeX 作为初始渲染后端

Status: implemented

[中文](./2026-09-03-latex-as-initial-rendering-backend.md) | [English](./2026-09-03-latex-as-initial-rendering-backend.en.md)

## 问题

重建与翻译后的论文从第一天起就必须渲染为 PDF，并支持 Unicode、多语言与数学。

## 决策

LaTeX 是唯一的一等渲染后端。LuaLaTeX 是默认引擎。latexmk 驱动编译。一等模板位于 `templates/latex/`。SemanticDocument 仍是真源；LaTeX 是投影。Typst 有意推迟，不安装、不提供模板，也不宣传为当前能力。

## 考虑过的替代方案

- 一开始就做通用 Renderer 接口是臆测。
- 以 pdfLaTeX 为主会无法满足 Unicode 与 CJK。
- 在 bootstrap 时安装 Typst 会暗示存在第二个尚未落地的渲染器。

## 后果

渲染工作遵循 `.agents/skills/latex-rendering/SKILL.md`。引入 Typst 或双渲染器设计，需要一份 proposed architecture Agent Note，覆盖规范渲染器、映射、公式、模板与维护成本。
