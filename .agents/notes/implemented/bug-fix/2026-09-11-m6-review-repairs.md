# Agent Note: M6 Review 修复

Status: implemented

[中文](./2026-09-11-m6-review-repairs.md) | [English](./2026-09-11-m6-review-repairs.en.md)

## 问题

2026-09-11 Code Review 认定 M6 可保留「功能基线落地」，但在进入 M7 前必须修复重译正确性、异步渲染与数据发布一致性。本 Note 补充既有 [M6 Bidirectional Reader 落地](../feature/2026-09-11-m6-bidirectional-reader.md)，不引入字符级 mapping、MathML、矢量图或 parser specialist。

## 决策

1. **Provider 身份**：`rerender_workspace` 把 `_build_translation_provider` 返回的实际 `provider_model` / endpoint 传入 `retranslate_nodes`。新 entry 记录实际模型；层字段是最近一次翻译 pass 的身份，混合模型时以 entry 为准。真实 workspace（层或任一 entry 非 dummy）在当前配置缺失 provider 时抛 `TranslationProviderNotConfiguredError`（API 503），禁止用 dummy 覆盖真实译文。
2. **强制重译**：用户发起的 `retranslate_nodes` 对所选节点 `skip_cache_read=True`，成功后仍写入缓存；未选节点保持原文。缓存键继续包含 model 与 endpoint，同 endpoint 换模型不会命中旧结果。
3. **渲染并发**：每侧 `PaneRenderer` / `ExclusiveRenderer` 取消旧 PDF.js `RenderTask` 并等待退出，只让最新 generation 提交 canvas、页码与几何。同页选择变化只重画 overlay。
4. **产物一致性**：编译、锚点恢复与 `validate_bundle_references` 在暂存 `build/.rerender-*` 完成；通过后先写入 `revisions/<id>/` 再原子替换 `manifest.json`，最后更新稳定别名。失败保留上一完整 revision。workspace JSON 在 viewer 发布成功后才替换。Vite `serve-public-data` 按请求从 `public/data` 提供 `/data/*`，避免启动后新建的 revision 目录被 SPA fallback 成 `index.html`。
5. **前端刷新**：先完整加载候选 mapping/meta/PDF 再切换；revision URL 若返回 HTML/非 JSON，回退到带同一 revision cache-buster 的稳定别名。任一步失败回滚并销毁候选。`retranslateBusy` 提升到阅读器层，切换节点不能并发重译。`#viewer` 暴露 `data-busy` / `data-revision`。
6. **Unicode 偏移**：marks 使用 Unicode code point；Inspector 经 `sliceByCodePoint` 切片，覆盖数学字母与补充汉字。
7. **HTTP 边界**：拒绝负 `Content-Length`（400）；超限 413；读取超时 408。
8. **E2E**：每次点击绑定对应 `waitForResponse`，等待 busy→idle 与新 revision。
9. **`pickCounterpart`**：仍是节点内落点启发式（绑定决定身份；缺字符级 mapping 时用页码/y）。不改算法；补充两侧分页显著不同的样例。点击走 `hitTest` 最小面积优先；`setActiveNode` 统一刷新 Inspector。

## 考虑过的替代方案

- 层 `providerModel` 在混合时写成 `"mixed"`：schema 无枚举约束，但会让现有 dummy 比较失败；最近 pass + entry 权威更清晰。
- 用符号链接做 viewer 当前指针：Windows/Vite 静态服务不稳；`manifest.json` 原子替换足够。
- 把 `pickCounterpart` 改为永远落在节点起始 fragment：会破坏同步滚动的条带对应，留给字符级 mapping。

## 后果

- 重译不再把模型 B 的译文标成模型 A，也不会在缺配置时用 dummy 冒充真实模型。
- 连续翻页/点击/同步滚动不再让两个 RenderTask 共用一块 canvas。
- 编译、校验或发布失败后，上一 revision 的 PDF/mapping/meta 仍可阅读。
- 当前态：[阅读器](../../../../docs/architecture/reader.md)。延期项不变。
