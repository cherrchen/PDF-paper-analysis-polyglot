# Agent Note: M5 Review 修复

Status: implemented

[中文](./2026-09-08-m5-review-repairs.md) | [English](./2026-09-08-m5-review-repairs.en.md)

## 问题

2026-09-08 Code Review 认定 M5 不能验收。已声明的翻译、图资源、公式、表格、中文排版与 RenderAnchor 能力在真实路径上丢失内容、编译失败或映射错误；现有绿色测试未覆盖这些情形。本 Note 补充既有 [M5 Translation & Rendering Pipeline 落地 Note](../architecture/2026-09-08-m5-translation-rendering-pipeline.md)，不重做 schema，也不引入 MathML / 双栏 profile / 1→N Semantic。

## 决策

1. **翻译保护**：`OpenAICompatProvider` 先把 CITATION / 公式等 marks 换成占位符再请求模型，并校验返回占位符完整性；dummy 路径行为不变。
2. **术语缓存**：真实 provider 也按术语表内容计算 `terminologyRevision`，手工译文变更会使缓存失效。
3. **Provider 配置**：`create_provider(provider_config=...)` 与 `run_pipeline(translation_config=...)` 直接使用传入配置，不再二次读取环境变量覆盖端点或模型。
4. **中文排版**：`generic-academic.tex` 用 `luatexja-fontspec` + FandolSong，默认 `zh-CN` 译文可显示；回归检查编译日志无 Missing character。
5. **公式**：unicode 符号替换后给控制序列加 `{}` 边界；无法安全转换则回退 `\text{...}`；`equation.number` 以 `\tag` 保留源编号。
6. **图资源**：提取 FlateDecode 等位图（无 PIL 时走 bitmap→PNG）；ResourceID 与 physical `imageObject` 对齐；按 layout `physicalObjectIds` 绑定，禁止按全局序号猜测；无法提取时记 Issue 并输出可观察空框。
7. **浮动锚点**：figure/table 的起止 hypertarget 放在浮动环境内，随内容移动。
8. **表格**：`floatTables=False` 使用 `\captionof`（ABOVE/BELOW）；按完整网格投影 `rowSpan`/`colSpan` 与空列；`SCALE_FONT` 走 `\fitbox`。
9. **溢出**：默认 `SCALE_DOWN` 公式走 `\fitmath`，宽表超过 `\linewidth` 才缩放。
10. **图像路径**：写入 TeX 前解析为绝对路径，避免相对 `out_dir` 在 `build/` 下找不到文件。
11. **RenderAnchor**：由起止 hypertarget 插值生成覆盖各页内容区的 geometry，不再只留下两端 12×12 命中框。

## 考虑过的替代方案

- 继续用全局第 N 张图填充第 N 个 FIGURE：页眉图、矢量图、被跳过的 PNG 会张冠李戴。
- 用 `ctex` 做中文：依赖包含 beamer / xetex / uplatex，CI 宏包集过大；`luatexja` + `fandol` 足够显示与断行。
- 为位图提取加入 Pillow：仓库要保持小依赖；PDFium bitmap + 标准库 PNG 编码即可。
- 在正文插入位置保留图表锚点：浮动体移走后跳转错误页面。

## 后果

- M5 验收阻塞项（保护文本、中文缺字、非法公式命令、PNG 丢弃、跨页 fragment、错误配图、浮动锚点、公式重编号）有机械测试。
- 已知延期不变：MathML、`dense-two-column`、1 Layout → N Semantic、矢量图 PDF/SVG 真源。
- 当前态：[渲染](../../../../docs/architecture/rendering.md)；宏包：[LaTeX](../../../../docs/development/latex.md)。
