# Agent Note: M8 P2 阅读器首屏事务

Status: implemented

[中文](./2026-09-16-m8-p2-reader-load.md) | [English](./2026-09-16-m8-p2-reader-load.en.md)

## 问题

导入 load 在首屏渲染前替换状态，getPage 或 render 失败留下混合修订。

## 决策

两侧首屏使用 PaneRenderer 离屏渲染，等待全部结束才提交状态与画面。准备失败销毁候选 PDF，保留旧 PDF、页码、选择、滚动、焦点与 Inspector；成功后销毁旧 PDF。

## 考虑过的替代方案

切换后重绘旧 PDF 的回滚本身也可能失败，并短暂展示混合文档。

## 后果

测试直接调用真实 load 和 PaneRenderer，覆盖 getPage 失败、render 失败和成功；延迟另一侧渲染验证清理时序。补充 [P1 修复](2026-09-16-m8-p1-concurrency-and-binding.md)，不改变既有重译加载流程。当前态见[阅读器](../../../../docs/architecture/reader.md)。
