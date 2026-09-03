# Agent Note: 源码可得的 MIT 加非商用条款

Status: implemented

[中文](./2026-09-03-source-available-noncommercial-license.md) | [English](./2026-09-03-source-available-noncommercial-license.en.md)

## 问题

项目应易于阅读、为研究而 fork、并接受贡献，但不授予商用权利。

## 决策

仓库使用 MIT 许可证正文，外加禁止商用的附加条款。允许个人、学术、教育、研究与内部评估使用。商用需要另行书面许可。包元数据指向 `LICENSE`，不声称未经修改的 OSI 认可 MIT。

## 考虑过的替代方案

- 未经修改的 MIT 会允许商用，这不是想要的。
- Apache-2.0 同样允许商用，并增加专利授权，却解决不了商用限制。
- CC BY-NC 不适合软件。
- PolyForm Noncommercial 是为此目的设计的，但不是所要求的 MIT 形态授权。

## 后果

这是源码可得，不是 OSI 开源。下游必须同时保留 MIT 声明与非商用附加条款。`cargo-deny` 仍允许 MIT/Apache 依赖；它不会把本仓库重新分类为 MIT。
