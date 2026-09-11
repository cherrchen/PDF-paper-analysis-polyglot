# Agent Note: M5 内容保真与配置兑现修复

Status: implemented

[中文](./2026-09-11-m5-fidelity-repairs.md) | [English](./2026-09-11-m5-fidelity-repairs.en.md)

## 问题

2026-09-11 审计认定 M5 可保留「基线落地」，但尚不足以通过「可靠翻译、完整学术内容、自然重排」验收。架构分层合理，缺口集中在内容保真、异常输入与配置兑现：非法上下标与未转义 `$` 可使整篇 PDF 编译失败；根号转换把 `√x` 写成 `\sqrt{}x`；多资源 Figure 只投影第一张图；注入的 `httpx.Client` 第一次请求后被关闭；占位符只检查缺失并允许重复进入译文与缓存；缓存键缺少 endpoint / 上下文 / 提示词版本；`RenderPolicy` 部分枚举被 schema 接受后静默忽略。

本 Note 补充 [M5 Translation & Rendering Pipeline 落地](../architecture/2026-09-08-m5-translation-rendering-pipeline.md) 与 [M5 Review 修复](./2026-09-08-m5-review-repairs.md)，不重做 schema，也不引入 MathML、`dense-two-column` 或 1 Layout→N Semantic。

## 决策

1. **公式**：只解析可识别的上下标与根号作用范围；独立符号仍加 `{}` 边界；无法确定时整段进入完整转义的 `\text{...}`（含 `$`）。`√x` / `√12` / `√(...)` 转为 `\sqrt{...}`，`√xy` 等歧义保留原文。
2. **多图**：投影全部已绑定资源；无法恢复 subfigure 布局时纵向堆叠，并写 `RENDERING` Issue。
3. **HTTP 客户端**：外部注入的 `httpx.Client` 由调用方关闭；provider 只对内部临时客户端使用 `with`。
4. **占位符**：使用不与原文 `⟦n⟧` 碰撞的 `⟦n:m⟧` 方案；按编号与出现次数校验；重复、新增或丢失均拒绝；失败结果不写入缓存。
5. **缓存键**：稳定摘要包含节点内容、locale、模型名、endpoint、术语修订、候选术语、提示词版本与翻译上下文。不写入 API key。
6. **RenderPolicy**：figure/table 的 `captionPosition`（含 `SOURCE` 近似并记 Issue）、`wideFigureHandling`（`SCALE_DOWN` / `WIDE_FLOAT` / `INLINE`）、`tableOverflowHandling`（`SCALE_FONT` / `WIDE_FLOAT` / `WRAP` / `FAIL`）均参与投影。`MULTILINE` 公式无断行点时降级为 `SCALE_DOWN` 并记 Issue；`TRUNCATE` 以 `\makebox` 裁切。
7. **术语**：dummy 仍生成 `[TERM]` 优选译文；真实 provider 把发现的短语作为一致性候选送入提示词，不编造优选译文。
8. **工程**：PDFium / Chat Completions 解析收到小型适配函数；语义树遍历共享；翻译上下文改为邻近索引而非对每个节点扫描后续全文。

## 考虑过的替代方案

- 继续用字符白名单把 `^_` 当安全数学：`x__1` 能通过「安全」检查却无法编译。
- 根号一律加 `{}`：能编译但改变数学含义，现有「编译成功」检查发现不了。
- 多图只渲染第一张并推迟到矢量图能力：丢失的是已提取位图，不是延期能力。
- 把注入客户端放进 `with`：重试与第二次请求都会 `Cannot reopen a client instance`。
- 缓存只键模型名：同名模型换 endpoint 或改邻段上下文会命中旧译文。

## 后果

- 异常公式、多资源 Figure、占位符重复、注入客户端复用、缓存指纹与策略枚举有机械测试；公式回归包含真实 LuaLaTeX 编译。
- M5 仍是基线而非完整 Exit Gate：`source-derived` / `dense-two-column`、MathML、矢量图 PDF/SVG、1 Layout→N Semantic 保持延期。
- 当前态：[渲染](../../../../docs/architecture/rendering.md)；路线图：[roadmap](../../../../docs/development/roadmap.md)。
