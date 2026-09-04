# Agent Note: M2 Review 修复与重新验收

Status: implemented

[中文](./2026-09-05-m2-review-repairs.md) | [English](./2026-09-05-m2-review-repairs.en.md)

## 问题

2026-09-05 Code Review 发现 M2 Walking Skeleton 虽通过当时的 `just check`，但没有满足 Roadmap Exit Gate：Viewer 未实现双向点击，Tier-1 PDF 全链并非全部可编译，FigureRegion reading flow 不完整，旋转页坐标变换错误，翻译与渲染绕过冻结契约，相关 E2E 也未进入 clean-checkout CI。

本 Note 补充既有 [M2 Walking Skeleton 落地 Note](../architecture/2026-09-04-m2-walking-skeleton.md)，保留其中 PDFium、基础 recovery、LaTeX 与 PDF.js 选型，并修正其最初的完成依据。

## 决策

M2 按原 Exit Gate 修复并重新验收：

1. Physical page-space 按 0/90/180/270° 建立逐页正反矩阵，所有 PDFium 对象通过矩阵进入 top-left canonical space。
2. Layout reading flow 同时包含 text 与 figure region；Semantic recovery 从这一完整 flow 建树。
3. 新增 canonical TranslationLayer 与 RenderDocument schema 及生成绑定。翻译只写 TranslationLayer，RenderComposer 合成 RenderDocument，LaTeX backend 只消费 RenderDocument。
4. PDF 文本进入 LaTeX 前清理非法 C0 控制字符；`CAPTION_OF` figure/caption 合成为同一个 render block 与 LaTeX float。
5. RenderAnchor 使用可命中的矩形；版本化 Viewer 数据包含 source region、semantic kind 与 target anchor。
6. Viewer 实现双向点击、高亮和跨页切换；`just test-e2e` 自行编译 fixture、运行管线和构建应用，并在 LaTeX CI job 中执行。
7. Pyright 不再对整个 pdf-pipeline/llm 包降级，只在直接接触无完整类型桩的 PDFium 适配文件中局部抑制 Unknown 诊断。

## 考虑过的替代方案

- 保持 M2“已完成”并把问题推迟到 M3：会让 M3 建立在错误坐标、丢失 Figure 与虚假 Viewer 验收之上。
- 只修改文档，将未实现功能声明为限制：Roadmap 2.7 与 Exit Gate 明确要求真正双向导航，不能降级为映射数组存在。
- 继续使用翻译后的 SemanticDocument 副本：违反冻结的 origin semantics 与 TranslationLayer 身份模型。

## 后果

- 全部 11 个 Tier-1 fixture 通过 Physical→Layout→Semantic→Translation→Render→Target PDF 管线。
- Heading、Paragraph、FigureCaption 的 source↔target 映射进入真实 Playwright 点击回归；4 个 E2E 测试通过。
- `just check` 通过：137 个常规 Python 测试、21 个 integration 测试、golden、TypeScript、Rust、LaTeX、schema 与 docs 门禁全绿；Python 覆盖率 94%。
- `just security` 通过；`cargo deny` 仅保留既有未命中 license allowance 警告。本机没有 zizmor，CI 继续运行官方 action。
- Canonical schema 从原有集合增加 TranslationLayer 与 RenderDocument；生成器重跑前后产物哈希不变，Python/TypeScript 跨语言 roundtrip 覆盖两者。
- M2 Exit Gate 重新关闭，Roadmap 的下一阶段恢复为 M3。
